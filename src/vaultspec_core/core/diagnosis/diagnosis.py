"""Dataclasses aggregating diagnostic signals for providers and workspaces."""

from __future__ import annotations

from dataclasses import dataclass, field
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
