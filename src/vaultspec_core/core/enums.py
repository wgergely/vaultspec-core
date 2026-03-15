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


class Resource(StrEnum):
    """Managed spec resource types."""

    RULES = "rules"
    AGENTS = "agents"
    SKILLS = "skills"
    SYSTEM = "system"
    TEMPLATES = "templates"
    HOOKS = "hooks"


class FileName(StrEnum):
    """Canonical filenames for framework documentation and configuration."""

    FRAMEWORK = "framework.md"
    PROJECT = "project.md"
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
