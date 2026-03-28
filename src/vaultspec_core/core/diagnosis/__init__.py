"""Workspace and provider diagnostic types.

Re-exports the signal enums from :mod:`.signals`, the dataclasses from
:mod:`.diagnosis`, and the resolution engine from :mod:`..resolver` so
consumers can import directly from the package.
"""

from __future__ import annotations

from ..resolver import ResolutionPlan, ResolutionStep, resolve
from .diagnosis import ProviderDiagnosis, WorkspaceDiagnosis, diagnose
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
    "ResolutionPlan",
    "ResolutionStep",
    "WorkspaceDiagnosis",
    "diagnose",
    "resolve",
]
