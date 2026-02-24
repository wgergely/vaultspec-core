"""Centralized enums for tool types, resource types, and framework constants."""

from __future__ import annotations

from enum import StrEnum


class Tool(StrEnum):
    """Supported AI tool destinations."""

    CLAUDE = "claude"
    GEMINI = "gemini"
    AGENTS = "agents"  # For AGENTS.md sync
    ANTIGRAVITY = "antigravity"


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
    AGENTS = ".agents"
