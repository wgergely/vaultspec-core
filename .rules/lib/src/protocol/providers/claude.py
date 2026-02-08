from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from .base import AgentProvider, CapabilityLevel, ProcessSpec, resolve_includes

if TYPE_CHECKING:
    import pathlib


class ClaudeProvider(AgentProvider):
    """Provider for Anthropic Claude models via Claude CLI."""

    @property
    def name(self) -> str:
        return "claude"

    @property
    def supported_models(self) -> list[str]:
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ]

    def get_model_capability(self, model: str) -> CapabilityLevel:
        if "opus" in model:
            return CapabilityLevel.HIGH
        if "sonnet" in model:
            return CapabilityLevel.MEDIUM
        return CapabilityLevel.LOW

    def get_best_model_for_capability(self, level: CapabilityLevel) -> str:
        if level >= CapabilityLevel.HIGH:
            return "claude-3-opus-20240229"
        if level >= CapabilityLevel.MEDIUM:
            return "claude-3-5-sonnet-20241022"
        return "claude-3-5-haiku-20241022"

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Loads and resolves nested rules from .claude/rules/."""
        rules_dir = root_dir / ".claude" / "rules"
        if not rules_dir.exists():
            return ""

        all_rules = []
        for rule_file in sorted(rules_dir.glob("*.md")):
            content = rule_file.read_text(encoding="utf-8")
            resolved = resolve_includes(content, root_dir, rules_dir)
            all_rules.append(resolved)

        return "\n\n".join(all_rules)

    def prepare_process(
        self,
        agent_name: str,
        agent_meta: dict[str, str],
        agent_persona: str,
        task_context: str,
        root_dir: pathlib.Path,
        model_override: str | None = None,
    ) -> ProcessSpec:
        #  Load Rules (ensure they are loadable even if not used in CLI args)
        _rules = self.load_rules(root_dir)

        #  Locate executable
        executable = shutil.which("claude") or "claude"

        #  Prepare Environment
        env = os.environ.copy()
        # Claude CLI doesn't use a system prompt file the same way as Gemini
        # It relies on the persona defined in its internal config.

        return ProcessSpec(
            executable=executable,
            args=["mcp", "serve"],
            env=env,
            cleanup_paths=[],
        )
