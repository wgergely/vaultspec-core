"""Define the canonical enum vocabulary shared across core configuration.

This module holds the stable symbolic names for tools, resource kinds,
filenames, directory names, and model capability tiers. It serves as a schema
layer for the rest of the package rather than a workflow or execution module.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class CapabilityLevel(IntEnum):
    """Tiered capability levels used to select an appropriate model."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


class ClaudeModels(StrEnum):
    """Single source of truth for Claude model identifiers."""

    HIGH = "claude-opus-4-6"
    MEDIUM = "claude-sonnet-4-6"
    LOW = "claude-haiku-4-5"

    @classmethod
    def from_level(cls, level: CapabilityLevel) -> ClaudeModels:
        """Return the Claude model for a given :class:`CapabilityLevel`.

        Args:
            level: Desired capability tier.

        Returns:
            Corresponding :class:`ClaudeModels` member; defaults to ``MEDIUM``
            for any unmapped level.
        """
        mapping = {
            CapabilityLevel.HIGH: cls.HIGH,
            CapabilityLevel.MEDIUM: cls.MEDIUM,
            CapabilityLevel.LOW: cls.LOW,
        }
        return mapping.get(level, cls.MEDIUM)


class GeminiModels(StrEnum):
    """Single source of truth for Gemini model identifiers."""

    HIGH = "gemini-3-pro-preview"
    MEDIUM = "gemini-3-flash-preview"
    LOW = "gemini-2.5-flash"

    @classmethod
    def from_level(cls, level: CapabilityLevel) -> GeminiModels:
        """Return the Gemini model for a given :class:`CapabilityLevel`.

        Args:
            level: Desired capability tier.

        Returns:
            Corresponding :class:`GeminiModels` member; defaults to ``MEDIUM``
            for any unmapped level.
        """
        mapping = {
            CapabilityLevel.HIGH: cls.HIGH,
            CapabilityLevel.MEDIUM: cls.MEDIUM,
            CapabilityLevel.LOW: cls.LOW,
        }
        return mapping.get(level, cls.MEDIUM)


ModelRegistry = type[ClaudeModels] | type[GeminiModels]


class Tool(StrEnum):
    """Supported AI tool destinations."""

    CLAUDE = "claude"
    GEMINI = "gemini"
    ANTIGRAVITY = "antigravity"
    CODEX = "codex"


class ProviderCapability(StrEnum):
    """Capabilities a provider can declare support for."""

    RULES = "rules"
    SKILLS = "skills"
    AGENTS = "agents"
    ROOT_CONFIG = "root_config"
    SYSTEM = "system"
    HOOKS = "hooks"
    TEAMS = "teams"
    SCHEDULED_TASKS = "scheduled_tasks"
    WORKFLOWS = "workflows"


class Resource(StrEnum):
    """Managed spec resource types."""

    RULES = "rules"
    AGENTS = "agents"
    SKILLS = "skills"
    SYSTEM = "system"
    TEMPLATES = "templates"
    HOOKS = "hooks"
    WORKFLOWS = "workflows"
    MCPS = "mcps"


class FileName(StrEnum):
    """Canonical filenames for framework documentation and configuration."""

    CONFIG_TOML = "config.toml"
    CLAUDE = "CLAUDE.md"
    GEMINI = "GEMINI.md"
    AGENTS = "AGENTS.md"
    SKILL = "SKILL.md"
    SYSTEM = "SYSTEM.md"


class DirName(StrEnum):
    """Reserved directory names within the workspace."""

    VAULT = ".vault"
    VAULTSPEC = ".vaultspec"
    CLAUDE = ".claude"
    GEMINI = ".gemini"
    ANTIGRAVITY = ".agents"
    CODEX = ".codex"


class ManagedState(StrEnum):
    """Desired state of a managed workspace artifact."""

    PRESENT = "present"
    ABSENT = "absent"


class CliAction(StrEnum):
    """CLI action passed to the resolver and preflight engine."""

    INSTALL = "install"
    UPGRADE = "upgrade"
    SYNC = "sync"
    UNINSTALL = "uninstall"
    DOCTOR = "doctor"


class PrecommitHook(StrEnum):
    """Canonical pre-commit hook IDs managed by vaultspec-core.

    ``VAULT_FIX`` runs all vault checkers with ``--fix``, auto-repairing
    safe issues (naming, frontmatter, links, dangling, references, schema)
    and blocking on remaining errors (body-links).

    ``SPEC_CHECK`` runs the workspace doctor, diagnosing framework,
    provider, and tooling health.

    ``CHECK_PROVIDER_ARTIFACTS`` prevents provider artifacts and
    installation manifests from being committed to git.
    """

    VAULT_FIX = "vault-fix"
    SPEC_CHECK = "spec-check"
    CHECK_PROVIDER_ARTIFACTS = "check-provider-artifacts"
