"""Resolution engine that maps diagnosed workspace state to corrective actions.

Takes a :class:`~vaultspec_core.core.diagnosis.WorkspaceDiagnosis` and a
requested CLI action, then produces a :class:`ResolutionPlan` of ordered steps,
warnings, and blocking conflicts. Follows the rule matrix defined in the
cli-ambiguous-states ADR.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .diagnosis.signals import (
    BuiltinVersionSignal,
    ConfigSignal,
    ContentSignal,
    FrameworkSignal,
    GitignoreSignal,
    ManifestEntrySignal,
    ProviderDirSignal,
    ResolutionAction,
)

logger = logging.getLogger(__name__)


@dataclass
class ResolutionStep:
    """A single corrective action within a :class:`ResolutionPlan`.

    Args:
        action: The :class:`~vaultspec_core.core.diagnosis.signals.ResolutionAction`
            to perform.
        target: What the action operates on (provider name, file path, etc.).
        reason: Human-readable explanation of why this step is needed.
    """

    action: ResolutionAction
    target: str
    reason: str


@dataclass
class ResolutionPlan:
    """Accumulated plan of resolution steps, warnings, and conflicts.

    Args:
        steps: Ordered list of :class:`ResolutionStep` to execute.
        warnings: Non-blocking advisories emitted before execution.
        conflicts: Blocking issues that prevent execution.
    """

    steps: list[ResolutionStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        """Return ``True`` if the plan has unresolved conflicts."""
        return len(self.conflicts) > 0


def resolve(
    diagnosis: WorkspaceDiagnosis,
    action: str,
    provider: str = "all",
    *,
    force: bool = False,
    dry_run: bool = False,
) -> ResolutionPlan:
    """Build a resolution plan from diagnosed workspace state.

    Evaluates the full rule matrix against the diagnosis signals and
    requested action. Framework-level rules are checked first, then
    per-provider rules, then cross-cutting concerns (builtins, gitignore).

    Args:
        diagnosis: Populated :class:`WorkspaceDiagnosis` from
            :func:`~vaultspec_core.core.diagnosis.diagnose`.
        action: CLI action being performed - one of ``"install"``,
            ``"sync"``, ``"uninstall"``.
        provider: Provider scope - ``"all"`` or a specific provider name.
        force: When ``True``, escalates warnings to corrective steps.
        dry_run: When ``True``, the plan is informational only.

    Returns:
        A :class:`ResolutionPlan` with steps, warnings, and conflicts.
    """
    _ = dry_run  # reserved for executor phase
    plan = ResolutionPlan()

    # Doctor only diagnoses; it never resolves.
    if action == "doctor":
        return plan

    # Upgrade = install semantics for framework rules, then sync for the rest.
    # Resolve framework rules with "install", everything else with "sync".
    fw_action = "install" if action == "upgrade" else action
    prov_action = "sync" if action == "upgrade" else action

    _resolve_framework(plan, diagnosis.framework, fw_action, force=force)
    _resolve_version_warning(plan, diagnosis)
    _resolve_builtin_version(plan, diagnosis.builtin_version, prov_action, force=force)
    _resolve_gitignore(plan, diagnosis.gitignore, prov_action, force=force)

    # Per-provider rules
    for tool, prov_diag in diagnosis.providers.items():
        if provider != "all" and tool.value != provider:
            continue
        name = tool.value
        _resolve_manifest_entry(
            plan,
            prov_diag.manifest_entry,
            name,
            prov_action,
            force=force,
        )
        _resolve_provider_dir(
            plan,
            prov_diag.dir_state,
            name,
            prov_action,
            force=force,
        )
        _resolve_content(
            plan,
            prov_diag.content,
            name,
            prov_action,
            force=force,
        )
        _resolve_config(
            plan,
            prov_diag.config,
            name,
            prov_action,
            force=force,
        )

    return plan


# ---------------------------------------------------------------------------
# Framework rules
# ---------------------------------------------------------------------------


def _resolve_framework(
    plan: ResolutionPlan,
    signal: FrameworkSignal,
    action: str,
    *,
    force: bool,
) -> None:
    """Apply framework-level resolution rules."""
    if signal == FrameworkSignal.PRESENT:
        return

    if signal == FrameworkSignal.MISSING:
        if action == "install":
            # Proceed normally - install will scaffold
            return
        if action == "sync":
            plan.conflicts.append(
                "Framework not installed. Run 'vaultspec-core install' first."
            )
            return
        if action == "uninstall":
            plan.warnings.append("Nothing to remove - framework is not installed.")
            return

    if signal == FrameworkSignal.CORRUPTED:
        if action == "install":
            if force:
                plan.steps.append(
                    ResolutionStep(
                        action=ResolutionAction.REPAIR_MANIFEST,
                        target="manifest",
                        reason="Manifest corrupted, repairing before install",
                    )
                )
            else:
                plan.conflicts.append("Manifest is corrupted. Use --force to repair.")
            return
        if action == "sync":
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.REPAIR_MANIFEST,
                    target="manifest",
                    reason="Manifest corrupted, repairing before sync",
                )
            )
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.SYNC,
                    target="all",
                    reason="Sync after manifest repair",
                )
            )
            return
        if action == "uninstall":
            if force:
                plan.steps.append(
                    ResolutionStep(
                        action=ResolutionAction.REPAIR_MANIFEST,
                        target="manifest",
                        reason="Corrupted manifest - repairing before uninstall",
                    )
                )
            else:
                plan.conflicts.append(
                    "Manifest is corrupted. Use --force to proceed with uninstall."
                )
            return

    logger.warning("Unhandled signal: %s for action %s", signal, action)


# ---------------------------------------------------------------------------
# Manifest entry rules
# ---------------------------------------------------------------------------


def _resolve_manifest_entry(
    plan: ResolutionPlan,
    signal: ManifestEntrySignal,
    tool_name: str,
    action: str,
    *,
    force: bool,
) -> None:
    """Apply manifest-entry resolution rules for a single provider."""
    if signal in (ManifestEntrySignal.COHERENT, ManifestEntrySignal.NOT_INSTALLED):
        return

    if signal == ManifestEntrySignal.ORPHANED and action in ("install", "sync"):
        plan.steps.append(
            ResolutionStep(
                action=ResolutionAction.SCAFFOLD,
                target=tool_name,
                reason=f"Provider '{tool_name}' in manifest but directory missing",
            )
        )
        if action == "sync":
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.SYNC,
                    target=tool_name,
                    reason=f"Sync after scaffolding '{tool_name}'",
                )
            )
        return

    if signal == ManifestEntrySignal.UNTRACKED:
        if action == "install":
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.ADOPT_DIRECTORY,
                    target=tool_name,
                    reason=f"Directory for '{tool_name}' exists but is not in manifest",
                )
            )
            return
        if action == "sync":
            if force:
                plan.steps.append(
                    ResolutionStep(
                        action=ResolutionAction.ADOPT_DIRECTORY,
                        target=tool_name,
                        reason=f"Adopting untracked directory for '{tool_name}'",
                    )
                )
                plan.steps.append(
                    ResolutionStep(
                        action=ResolutionAction.SYNC,
                        target=tool_name,
                        reason=f"Sync after adopting '{tool_name}'",
                    )
                )
            else:
                plan.warnings.append(
                    f"Provider '{tool_name}' has an untracked directory. "
                    f"Use --force to adopt and sync."
                )
            return
        if action == "uninstall":
            if force:
                plan.steps.append(
                    ResolutionStep(
                        action=ResolutionAction.REMOVE,
                        target=tool_name,
                        reason=f"Removing untracked directory for '{tool_name}'",
                    )
                )
            else:
                plan.conflicts.append(
                    f"Provider '{tool_name}' has an untracked directory. "
                    f"Use --force to remove."
                )
            return

    logger.warning("Unhandled signal: %s for action %s", signal, action)


# ---------------------------------------------------------------------------
# Provider directory rules
# ---------------------------------------------------------------------------


def _resolve_provider_dir(
    plan: ResolutionPlan,
    signal: ProviderDirSignal,
    tool_name: str,
    action: str,
    *,
    force: bool,
) -> None:
    """Apply provider-directory resolution rules for a single provider."""
    if signal in (ProviderDirSignal.COMPLETE, ProviderDirSignal.MISSING):
        return

    if signal == ProviderDirSignal.MIXED and action == "uninstall":
        if force:
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.REMOVE,
                    target=tool_name,
                    reason=f"Force-removing '{tool_name}' directory with mixed content",
                )
            )
        else:
            plan.conflicts.append(
                f"Provider '{tool_name}' directory contains user content. "
                f"Use --force to remove."
            )
        return

    is_syncable = signal in (ProviderDirSignal.EMPTY, ProviderDirSignal.PARTIAL)
    if is_syncable and action == "sync":
        plan.steps.append(
            ResolutionStep(
                action=ResolutionAction.SYNC,
                target=tool_name,
                reason=f"Provider '{tool_name}' directory is {signal.value}",
            )
        )
        return

    logger.warning("Unhandled signal: %s for action %s", signal, action)


# ---------------------------------------------------------------------------
# Content rules
# ---------------------------------------------------------------------------


def _resolve_content(
    plan: ResolutionPlan,
    content: dict[str, ContentSignal],
    tool_name: str,
    action: str,
    *,
    force: bool,
) -> None:
    """Apply per-resource content resolution rules for a single provider."""
    if action != "sync":
        return

    for resource, signal in content.items():
        if signal == ContentSignal.CLEAN:
            continue

        if signal == ContentSignal.STALE:
            if force:
                plan.steps.append(
                    ResolutionStep(
                        action=ResolutionAction.PRUNE,
                        target=f"{tool_name}:{resource}",
                        reason=f"Stale file '{resource}' has no source",
                    )
                )
            else:
                plan.warnings.append(
                    f"Stale file '{resource}' in '{tool_name}' has no source. "
                    f"Use --force to prune."
                )

        elif signal == ContentSignal.MISSING:
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.SYNC,
                    target=f"{tool_name}:{resource}",
                    reason=f"Missing file '{resource}' in '{tool_name}'",
                )
            )

        elif signal == ContentSignal.DIVERGED:
            if force:
                plan.steps.append(
                    ResolutionStep(
                        action=ResolutionAction.SYNC,
                        target=f"{tool_name}:{resource}",
                        reason=(
                            f"Overwriting diverged file '{resource}' in '{tool_name}'"
                        ),
                    )
                )
            else:
                plan.warnings.append(
                    f"File '{resource}' in '{tool_name}' has diverged from source. "
                    f"Use --force to overwrite."
                )

        else:
            logger.warning("Unhandled signal: %s for action %s", signal, action)


# ---------------------------------------------------------------------------
# Builtin version rules
# ---------------------------------------------------------------------------


def _resolve_builtin_version(
    plan: ResolutionPlan,
    signal: BuiltinVersionSignal,
    action: str,
    *,
    force: bool,
) -> None:
    """Apply builtin-version resolution rules."""
    if signal == BuiltinVersionSignal.CURRENT:
        return

    if signal == BuiltinVersionSignal.DELETED:
        plan.warnings.append(
            "Builtin resources have been deleted from .vaultspec/rules/."
        )
        if force and action == "sync":
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.SYNC,
                    target="builtins",
                    reason="Re-seed deleted builtin resources",
                )
            )
        return

    if signal == BuiltinVersionSignal.NO_SNAPSHOTS:
        plan.warnings.append(
            "No version baseline for builtins - cannot verify integrity."
        )
        return

    if signal == BuiltinVersionSignal.MODIFIED and action == "sync":
        if force:
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.SYNC,
                    target="builtins",
                    reason="Re-seeding modified builtins",
                )
            )
        else:
            plan.warnings.append(
                "Builtin files have been modified since install. "
                "Use --force to re-seed."
            )
        return

    logger.warning("Unhandled signal: %s for action %s", signal, action)


# ---------------------------------------------------------------------------
# Config rules
# ---------------------------------------------------------------------------


def _resolve_config(
    plan: ResolutionPlan,
    signal: ConfigSignal,
    tool_name: str,
    action: str,
    *,
    force: bool,
) -> None:
    """Apply config resolution rules for a single provider."""
    if action != "sync":
        return

    if signal in (ConfigSignal.OK, ConfigSignal.PARTIAL_MCP, ConfigSignal.USER_MCP):
        return

    if signal == ConfigSignal.MISSING:
        plan.steps.append(
            ResolutionStep(
                action=ResolutionAction.SYNC,
                target=f"{tool_name}:config",
                reason=f"Config file missing for '{tool_name}'",
            )
        )
        return

    if signal == ConfigSignal.FOREIGN:
        if force:
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.SYNC,
                    target=f"{tool_name}:config",
                    reason=f"Overwriting user-authored config for '{tool_name}'",
                )
            )
        else:
            plan.warnings.append(
                f"Config for '{tool_name}' appears user-authored. "
                f"Use --force to overwrite."
            )
        return

    logger.warning("Unhandled signal: %s for action %s", signal, action)


# ---------------------------------------------------------------------------
# Gitignore rules
# ---------------------------------------------------------------------------


def _resolve_gitignore(
    plan: ResolutionPlan,
    signal: GitignoreSignal,
    action: str,
    *,
    force: bool,
) -> None:
    """Apply gitignore resolution rules."""
    _ = force  # gitignore repairs are unconditional
    if signal in (GitignoreSignal.COMPLETE, GitignoreSignal.NO_FILE):
        return

    if signal == GitignoreSignal.PARTIAL:
        if action in ("install", "sync"):
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.REPAIR_GITIGNORE,
                    target=".gitignore",
                    reason="Managed block entries are stale, updating",
                )
            )
        return

    if signal == GitignoreSignal.CORRUPTED:
        plan.steps.append(
            ResolutionStep(
                action=ResolutionAction.REPAIR_GITIGNORE,
                target=".gitignore",
                reason="Gitignore managed block is corrupted",
            )
        )
        return

    if signal == GitignoreSignal.NO_ENTRIES and action == "install":
        plan.steps.append(
            ResolutionStep(
                action=ResolutionAction.REPAIR_GITIGNORE,
                target=".gitignore",
                reason="Gitignore has no managed entries",
            )
        )
        return

    logger.warning("Unhandled signal: %s for action %s", signal, action)


# ---------------------------------------------------------------------------
# Version mismatch warning
# ---------------------------------------------------------------------------


def _resolve_version_warning(
    plan: ResolutionPlan,
    diagnosis: WorkspaceDiagnosis,
) -> None:
    """Emit a warning if the manifest was written by a newer vaultspec-core."""
    if diagnosis.framework != FrameworkSignal.PRESENT:
        return

    try:
        from importlib.metadata import version as pkg_version

        running_version = pkg_version("vaultspec-core")
    except Exception:
        return

    try:
        from .types import get_context

        target = get_context().target_dir
    except LookupError:
        return

    try:
        from .manifest import read_manifest_data

        manifest = read_manifest_data(target)
    except Exception:
        return

    manifest_version = manifest.vaultspec_version
    if not manifest_version:
        return

    # Compare using tuple of parsed version segments
    try:
        running_parts = _parse_version_tuple(running_version)
        manifest_parts = _parse_version_tuple(manifest_version)
        if manifest_parts > running_parts:
            plan.warnings.append(
                f"Manifest was written by vaultspec-core {manifest_version}, "
                f"but running version is {running_version}."
            )
    except Exception:
        pass


def _parse_version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse a PEP 440 version string into a comparable integer tuple.

    Strips any pre/post/dev suffixes and splits on dots.

    Args:
        version_str: Version string like ``"0.1.4"`` or ``"1.2.3rc1"``.

    Returns:
        Tuple of integer version segments.
    """
    import re

    # Strip pre-release / post-release suffixes
    clean = re.split(r"[^0-9.]", version_str)[0].rstrip(".")
    return tuple(int(x) for x in clean.split("."))


if TYPE_CHECKING:
    from .diagnosis.diagnosis import WorkspaceDiagnosis
