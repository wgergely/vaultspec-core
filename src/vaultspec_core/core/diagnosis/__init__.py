"""Workspace and provider diagnostic types.

Re-exports the signal enums from :mod:`.signals` and the dataclasses from
:mod:`.diagnosis` so consumers can import directly from the package.
"""

from __future__ import annotations

from .diagnosis import ProviderDiagnosis, WorkspaceDiagnosis
from .signals import (
    BuiltinVersionSignal,
    ConfigSignal,
    ContentSignal,
    FrameworkSignal,
    GitignoreSignal,
    ManifestEntrySignal,
    ProviderDirSignal,
    ResolutionAction,
)

__all__ = [
    "BuiltinVersionSignal",
    "ConfigSignal",
    "ContentSignal",
    "FrameworkSignal",
    "GitignoreSignal",
    "ManifestEntrySignal",
    "ProviderDiagnosis",
    "ProviderDirSignal",
    "ResolutionAction",
    "WorkspaceDiagnosis",
]
