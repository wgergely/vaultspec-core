"""Signal enums for workspace and provider diagnosis.

Each enum encodes the observable state of a single diagnostic axis.
:class:`ResolutionAction` maps diagnosed states to corrective operations.
"""

from __future__ import annotations

from enum import StrEnum


class FrameworkSignal(StrEnum):
    """Observed state of the vaultspec framework directory."""

    MISSING = "missing"
    CORRUPTED = "corrupted"
    PRESENT = "present"


class ProviderDirSignal(StrEnum):
    """Observed state of a provider's configuration directory."""

    MISSING = "missing"
    EMPTY = "empty"
    PARTIAL = "partial"
    COMPLETE = "complete"
    MIXED = "mixed"


class ManifestEntrySignal(StrEnum):
    """Coherence between a provider directory and the manifest."""

    COHERENT = "coherent"
    ORPHANED = "orphaned"
    UNTRACKED = "untracked"
    NOT_INSTALLED = "not_installed"


class ContentSignal(StrEnum):
    """Content integrity of a managed resource file."""

    CLEAN = "clean"
    DIVERGED = "diverged"
    STALE = "stale"
    MISSING = "missing"


class BuiltinVersionSignal(StrEnum):
    """Version state of built-in resource snapshots."""

    CURRENT = "current"
    MODIFIED = "modified"
    DELETED = "deleted"
    NO_SNAPSHOTS = "no_snapshots"


class ConfigSignal(StrEnum):
    """Observed state of a provider's root configuration file."""

    OK = "ok"
    MISSING = "missing"
    FOREIGN = "foreign"
    PARTIAL_MCP = "partial_mcp"
    USER_MCP = "user_mcp"


class GitignoreSignal(StrEnum):
    """Observed state of gitignore entries for managed paths."""

    NO_FILE = "no_file"
    NO_ENTRIES = "no_entries"
    PARTIAL = "partial"
    COMPLETE = "complete"
    CORRUPTED = "corrupted"


class ResolutionAction(StrEnum):
    """Corrective action that a resolver can apply."""

    SCAFFOLD = "scaffold"
    SYNC = "sync"
    PRUNE = "prune"
    REPAIR_MANIFEST = "repair_manifest"
    ADOPT_DIRECTORY = "adopt_directory"
    REPAIR_GITIGNORE = "repair_gitignore"
    REMOVE = "remove"
    SKIP = "skip"
