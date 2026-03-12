"""Gemini execution provider for workspace-scoped prompts and rules.

This module implements the Gemini provider within the shared execution
protocol. Its specialization is the Gemini-specific loading of workspace
prompt and rules files, including ``@include`` expansion through the common
resolution helpers, without changing the underlying protocol contract, result
model, or capability semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib

    from ...core.enums import ModelRegistry

from ...core.enums import GeminiModels
from .base import (
    ExecutionProvider,
    resolve_includes,
)

__all__ = ["GeminiProvider"]


class GeminiProvider(ExecutionProvider):
    """Provider for Google Gemini models via the Gemini CLI ACP bridge.

    Handles system-prompt and rules loading from the workspace.
    """

    @property
    def name(self) -> str:
        """Return the provider identifier string.

        Returns:
            The string ``"gemini"``.
        """
        return "gemini"

    @property
    def models(self) -> ModelRegistry:
        """Return the Gemini model registry.

        Returns:
            The :class:`GeminiModels` registry class.
        """
        return GeminiModels

    def load_system_prompt(self, root_dir: pathlib.Path) -> str:
        """Load ``.gemini/SYSTEM.md`` if it exists (deployed by CLI sync).

        Args:
            root_dir: Workspace root directory.

        Returns:
            File contents as a string, or an empty string if the file is absent.
        """
        system_file = root_dir / ".gemini" / "SYSTEM.md"
        if not system_file.exists():
            return ""
        return system_file.read_text(encoding="utf-8")

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Load and inline-resolve rules from ``.gemini/rules/``.

        All ``*.md`` files in the rules directory are read in sorted order and
        their ``@include`` directives are resolved recursively.

        Args:
            root_dir: Workspace root directory.

        Returns:
            Concatenated rules text, or an empty string if the directory does
            not exist.
        """
        rules_dir = root_dir / ".gemini" / "rules"
        if not rules_dir.exists():
            return ""

        all_rules = []
        for rule_file in sorted(rules_dir.glob("*.md")):
            content = rule_file.read_text(encoding="utf-8")
            resolved = resolve_includes(content, rules_dir, root_dir)
            all_rules.append(resolved)

        return "\n\n".join(all_rules)
