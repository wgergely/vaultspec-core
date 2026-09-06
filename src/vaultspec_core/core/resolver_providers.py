"""Per-provider resolution rules.

Covers the four provider-scoped signal checks the orchestrator runs per tool:
manifest-entry coherence, provider directory completeness, per-resource content
drift, and root config file state. Split out of ``resolver.py`` as the rule
group evaluated once per configured provider.
"""

from __future__ import annotations

import logging
from typing import assert_never

from .diagnosis.signals import (
    ConfigSignal,
    ContentSignal,
    ManifestEntrySignal,
    ProviderDirSignal,
    ResolutionAction,
)
from .enums import CliAction
from .resolver_types import ResolutionPlan, ResolutionStep

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Manifest entry rules
# ---------------------------------------------------------------------------


def resolve_manifest_entry(
    plan: ResolutionPlan,
    signal: ManifestEntrySignal,
    tool_name: str,
    action: CliAction,
    *,
    force: bool,
) -> None:
    """Apply manifest-entry resolution rules for a single provider."""
    if signal in (ManifestEntrySignal.COHERENT, ManifestEntrySignal.NOT_INSTALLED):
        return

    if signal == ManifestEntrySignal.ORPHANED and action in (
        CliAction.INSTALL,
        CliAction.SYNC,
    ):
        plan.steps.append(
            ResolutionStep(
                action=ResolutionAction.SCAFFOLD,
                target=tool_name,
                reason=f"Provider '{tool_name}' in manifest but directory missing",
            )
        )
        if action == CliAction.SYNC:
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.SYNC,
                    target=tool_name,
                    reason=f"Sync after scaffolding '{tool_name}'",
                )
            )
        return

    if signal == ManifestEntrySignal.UNTRACKED:
        if action == CliAction.INSTALL:
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.ADOPT_DIRECTORY,
                    target=tool_name,
                    reason=f"Directory for '{tool_name}' exists but is not in manifest",
                )
            )
            return
        if action == CliAction.SYNC:
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
        if action == CliAction.UNINSTALL:
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

    if signal == ManifestEntrySignal.ORPHANED and action == CliAction.UNINSTALL:
        # Orphaned on uninstall: directory already missing, manifest entry
        # will be cleaned up by the uninstall command itself.
        return

    # All ManifestEntrySignal values are handled above.
    logger.warning("Unknown ManifestEntrySignal member: %s (action=%s)", signal, action)


# ---------------------------------------------------------------------------
# Provider directory rules
# ---------------------------------------------------------------------------


def resolve_provider_dir(
    plan: ResolutionPlan,
    signal: ProviderDirSignal,
    tool_name: str,
    action: CliAction,
    *,
    force: bool,
) -> None:
    """Apply provider-directory resolution rules for a single provider."""
    if signal in (ProviderDirSignal.COMPLETE, ProviderDirSignal.MISSING):
        return

    if signal == ProviderDirSignal.MIXED and action == CliAction.UNINSTALL:
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
                f"Provider '{tool_name}' directory contains files not managed "
                f"by vaultspec (user-created content outside rules/, skills/, "
                f"agents/ subdirectories). Use --force to remove."
            )
        return

    if signal == ProviderDirSignal.MIXED and action in (
        CliAction.INSTALL,
        CliAction.SYNC,
    ):
        # Mixed content during install/sync: the command will sync managed
        # resources without touching unrecognized files.
        return

    is_syncable = signal in (ProviderDirSignal.EMPTY, ProviderDirSignal.PARTIAL)
    if is_syncable and action == CliAction.SYNC:
        plan.steps.append(
            ResolutionStep(
                action=ResolutionAction.SYNC,
                target=tool_name,
                reason=f"Provider '{tool_name}' directory is {signal.value}",
            )
        )
        return

    if is_syncable and action in (CliAction.INSTALL, CliAction.UNINSTALL):
        # Empty/partial during install: install will scaffold and sync.
        # Empty/partial during uninstall: the directory will be removed.
        return

    # All ProviderDirSignal values are handled above.
    logger.warning("Unknown ProviderDirSignal member: %s (action=%s)", signal, action)


# ---------------------------------------------------------------------------
# Content rules
# ---------------------------------------------------------------------------


def resolve_content(
    plan: ResolutionPlan,
    content: dict[str, ContentSignal],
    tool_name: str,
    action: CliAction,
    *,
    force: bool,
) -> None:
    """Apply per-resource content resolution rules for a single provider."""
    if action != CliAction.SYNC:
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
            # All ContentSignal values are handled above.
            logger.warning(
                "Unknown ContentSignal member: %s (action=%s)", signal, action
            )


# ---------------------------------------------------------------------------
# Config rules
# ---------------------------------------------------------------------------


_ROOT_CONFIG_LABELS = {
    "claude": "CLAUDE.md",
    "gemini": "GEMINI.md",
    "antigravity": "GEMINI.md",
    "codex": "AGENTS.md",
}


def resolve_config(
    plan: ResolutionPlan,
    signal: ConfigSignal,
    tool_name: str,
    action: CliAction,
    *,
    force: bool,
) -> None:
    """Apply config resolution rules for a single provider."""
    if action != CliAction.SYNC:
        return

    if signal in (
        ConfigSignal.OK,
        ConfigSignal.PARTIAL_MCP,
        ConfigSignal.USER_MCP,
        ConfigSignal.REGISTRY_DRIFT,
    ):
        return

    if signal == ConfigSignal.MISSING:
        plan.steps.append(
            ResolutionStep(
                action=ResolutionAction.SYNC,
                target=f"{tool_name}:config",
                reason=(
                    f"Root config {_ROOT_CONFIG_LABELS.get(tool_name, 'config file')} "
                    f"missing for provider '{tool_name}'"
                ),
            )
        )
        return

    if signal == ConfigSignal.FOREIGN:
        if force:
            plan.steps.append(
                ResolutionStep(
                    action=ResolutionAction.SYNC,
                    target=f"{tool_name}:config",
                    reason=(
                        "Overwriting user-authored root config "
                        f"{_ROOT_CONFIG_LABELS.get(tool_name, 'config file')} "
                        f"for provider '{tool_name}'"
                    ),
                )
            )
        else:
            plan.warnings.append(
                f"Config for '{tool_name}' appears user-authored. "
                f"Use --force to overwrite."
            )
        return

    # A check that could not run has observed nothing about the config, so it
    # cannot justify a repair. `doctor` weighs it as a warning; preflight stays
    # its hand rather than rewriting a file on a guess (issue #407).
    if signal == ConfigSignal.UNREADABLE:
        return

    # Config resolution only applies to "sync" action; other actions handled
    # by the main command directly. Every ConfigSignal member is covered by
    # a branch above, so this is a check-time exhaustiveness guarantee, not
    # a runtime fallback: adding a member without a matching branch here is
    # now a type error rather than a silent warning.
    assert_never(signal)
