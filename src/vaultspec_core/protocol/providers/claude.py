"""Claude execution provider for workspace-scoped prompts and rules.

This module implements the Anthropic Claude provider within the generic
execution-provider contract. It applies Claude-specific workspace file
conventions for loading system prompts and rules while preserving the shared
protocol semantics, result types, and capability-tier model selection defined
by the base provider layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib

    from ...core.enums import ModelRegistry

from ...core.enums import ClaudeModels
from .base import (
    ExecutionProvider,
)

__all__ = ["ClaudeProvider"]


class ClaudeProvider(ExecutionProvider):
    """Provider for Anthropic Claude models via the Python ACP bridge.

    Handles system-prompt and rules loading from the workspace.
    """

    @property
    def name(self) -> str:
        """Return the provider identifier string.

        Returns:
            The string ``"claude"``.
        """
        return "claude"

    @property
    def models(self) -> ModelRegistry:
        """Return the Claude model registry.

        Returns:
            The :class:`ClaudeModels` registry class.
        """
        return ClaudeModels

    def load_system_prompt(self, root_dir: pathlib.Path) -> str:
        """Load ``.claude/CLAUDE.md`` if it exists (deployed by CLI sync).

        Args:
            root_dir: Workspace root directory.

        Returns:
            File contents as a string, or an empty string if the file is absent.
        """
        system_file = root_dir / ".claude" / "CLAUDE.md"
        if not system_file.exists():
            return ""
        return system_file.read_text(encoding="utf-8")

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Load rules from ``.claude/rules/``.

        Reads all ``*.md`` files in the rules directory in sorted order.
        Unlike Gemini, standard Claude instructions often prefer individual
        files; they are concatenated here for inclusion in the system prompt.

        Args:
            root_dir: Workspace root directory.

        Returns:
            Concatenated rules text, or an empty string if the directory does
            not exist.
        """
        rules_dir = root_dir / ".claude" / "rules"
        if not rules_dir.exists():
            return ""

        all_rules = []
        for rule_file in sorted(rules_dir.glob("*.md")):
            all_rules.append(rule_file.read_text(encoding="utf-8"))

        return "\n\n".join(all_rules)
