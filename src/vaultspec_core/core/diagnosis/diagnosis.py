"""Dataclasses aggregating diagnostic signals for providers and workspaces.

The :func:`diagnose` orchestrator drives layered signal collection, delegating
to the individual collectors in :mod:`.collectors`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..enums import Tool

from .signals import (
    BuiltinVersionSignal,
    ConfigSignal,
    ContentSignal,
    FrameworkSignal,
    GitignoreSignal,
    ManifestEntrySignal,
    ProviderDirSignal,
)

logger = logging.getLogger(__name__)


@dataclass
class ProviderDiagnosis:
    """Collected diagnostic signals for a single provider.

    Args:
        tool: The :class:`~vaultspec_core.core.enums.Tool` being diagnosed.
        dir_state: Observed state of the provider directory.
        manifest_entry: Coherence between directory and manifest.
        content: Per-resource :class:`ContentSignal` map.
        config: State of the provider's root configuration.
    """

    tool: Tool
    dir_state: ProviderDirSignal
    manifest_entry: ManifestEntrySignal
    content: dict[str, ContentSignal] = field(default_factory=dict)
    config: ConfigSignal = ConfigSignal.MISSING


@dataclass
class WorkspaceDiagnosis:
    """Top-level diagnosis aggregating framework and provider states.

    Args:
        framework: Observed state of the vaultspec framework directory.
        providers: Per-tool :class:`ProviderDiagnosis` map.
        builtin_version: Version state of built-in resource snapshots.
        gitignore: Observed state of gitignore entries.
    """

    framework: FrameworkSignal
    providers: dict[Tool, ProviderDiagnosis] = field(default_factory=dict)
    builtin_version: BuiltinVersionSignal = BuiltinVersionSignal.NO_SNAPSHOTS
    gitignore: GitignoreSignal = GitignoreSignal.NO_FILE


def diagnose(target: Path, *, scope: str = "full") -> WorkspaceDiagnosis:
    """Run layered diagnostic collection against a workspace.

    Args:
        target: Workspace root directory to diagnose.
        scope: Collection depth - ``"full"`` runs all collectors (doctor
            command), ``"framework"`` runs only framework presence and manifest
            coherence (install), ``"sync"`` adds provider dir, config, and
            gitignore checks.

    Returns:
        Populated :class:`WorkspaceDiagnosis` instance.
    """
    from ..enums import Tool
    from .collectors import (
        collect_builtin_version_state,
        collect_config_state,
        collect_content_integrity,
        collect_framework_presence,
        collect_gitignore_state,
        collect_manifest_coherence,
        collect_provider_dir_state,
    )

    # Layer 1: always collected
    try:
        framework = collect_framework_presence(target)
    except Exception:
        logger.warning("Framework presence collector failed", exc_info=True)
        framework = FrameworkSignal.MISSING

    try:
        gitignore = collect_gitignore_state(target)
    except Exception:
        logger.warning("Gitignore state collector failed", exc_info=True)
        gitignore = GitignoreSignal.NO_FILE

    diag = WorkspaceDiagnosis(framework=framework, gitignore=gitignore)

    if framework != FrameworkSignal.PRESENT:
        return diag

    # Layer 2: framework is PRESENT - collect manifest and builtin state
    manifest_map: dict[str, ManifestEntrySignal] = {}
    try:
        manifest_map = collect_manifest_coherence(target)
    except Exception:
        logger.warning("Manifest coherence collector failed", exc_info=True)

    try:
        diag.builtin_version = collect_builtin_version_state(target)
    except Exception:
        logger.warning("Builtin version collector failed", exc_info=True)

    if scope == "framework":
        # Build minimal provider entries from manifest data only
        for tool in Tool:
            entry = manifest_map.get(tool.value, ManifestEntrySignal.NOT_INSTALLED)
            diag.providers[tool] = ProviderDiagnosis(
                tool=tool,
                dir_state=ProviderDirSignal.MISSING,
                manifest_entry=entry,
            )
        return diag

    # Layer 3: scope is "full" or "sync" - collect per-provider details
    for tool in Tool:
        entry = manifest_map.get(tool.value, ManifestEntrySignal.NOT_INSTALLED)

        try:
            dir_state = collect_provider_dir_state(target, tool.value)
        except Exception:
            logger.warning(
                "Provider dir collector failed for %s", tool.value, exc_info=True
            )
            dir_state = ProviderDirSignal.MISSING

        try:
            config = collect_config_state(target, tool.value)
        except Exception:
            logger.warning(
                "Config state collector failed for %s", tool.value, exc_info=True
            )
            config = ConfigSignal.MISSING

        content: dict[str, ContentSignal] = {}
        if scope == "full":
            # Layer 4: full scope only - content integrity
            try:
                content = collect_content_integrity(target, tool.value)
            except Exception:
                logger.warning(
                    "Content integrity collector failed for %s",
                    tool.value,
                    exc_info=True,
                )

        diag.providers[tool] = ProviderDiagnosis(
            tool=tool,
            dir_state=dir_state,
            manifest_entry=entry,
            content=content,
            config=config,
        )

    return diag
