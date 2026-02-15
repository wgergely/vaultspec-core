from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from .base import (
    AgentProvider,
    CapabilityLevel,
    ClaudeModels,
    ModelRegistry,
    ProcessSpec,
    resolve_includes,
)

if TYPE_CHECKING:
    import pathlib


class ClaudeProvider(AgentProvider):
    """Provider for Anthropic Claude models via Python ACP bridge."""

    @property
    def name(self) -> str:
        return "claude"

    @property
    def models(self) -> ModelRegistry:
        return ClaudeModels

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Loads and resolves nested rules from .claude/rules/."""
        rules_dir = root_dir / ".claude" / "rules"
        if not rules_dir.exists():
            return ""

        all_rules = []
        for rule_file in sorted(rules_dir.glob("*.md")):
            content = rule_file.read_text(encoding="utf-8")
            resolved = resolve_includes(content, rules_dir, root_dir)
            all_rules.append(resolved)

        return "\n\n".join(all_rules)

    def _build_system_context(self, persona: str, rules: str) -> str:
        """Combine persona and rules into system context for initial prompt."""
        parts = []
        if persona.strip():
            parts.append(f"# AGENT PERSONA\n{persona}")
        if rules.strip():
            parts.append(f"# SYSTEM RULES & CONTEXT\n{rules}")
        return "\n\n".join(parts)

    def prepare_process(
        self,
        agent_name: str,
        agent_meta: dict[str, str],
        agent_persona: str,
        task_context: str,
        root_dir: pathlib.Path,
        model_override: str | None = None,
    ) -> ProcessSpec:
        _ = agent_name

        # Load rules
        rules = self.load_rules(root_dir)

        # Construct system context (persona + rules)
        system_context = self._build_system_context(agent_persona, rules)

        # Determine model
        model = model_override or agent_meta.get("model")
        if not model:
            tier = agent_meta.get("tier", "MEDIUM")
            model = self.get_best_model_for_capability(CapabilityLevel[tier.upper()])

        # Prepare environment — strip CLAUDECODE to unblock nested sessions
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env["VS_ROOT_DIR"] = str(root_dir)

        # Build initial prompt with system context prepended to task
        initial_prompt = (
            f"{system_context}\n\n# TASK\n{task_context}"
            if system_context
            else task_context
        )

        return ProcessSpec(
            executable=sys.executable,
            args=["-m", "protocol.acp.claude_bridge", "--model", model],
            env=env,
            cleanup_paths=[],
            initial_prompt_override=initial_prompt,
            session_meta={"model": model},
        )
