from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

# Features only supported by the Gemini provider
_GEMINI_ONLY_FEATURES = ("approval_mode",)


class ClaudeProvider(AgentProvider):
    """Provider for Anthropic Claude models via Python ACP bridge."""

    @property
    def name(self) -> str:
        return "claude"

    @property
    def models(self) -> ModelRegistry:
        return ClaudeModels

    def load_system_prompt(self, root_dir: pathlib.Path) -> str:
        """Load .claude/CLAUDE.md if it exists."""
        system_file = root_dir / ".claude" / "CLAUDE.md"
        if not system_file.exists():
            return ""
        return system_file.read_text(encoding="utf-8")

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

    def prepare_process(
        self,
        agent_name: str,
        agent_meta: dict[str, str],
        agent_persona: str,
        task_context: str,
        root_dir: pathlib.Path,
        model_override: str | None = None,
        mode: str = "read-write",
    ) -> ProcessSpec:
        _ = agent_name

        # Warn on Gemini-only features
        for key in _GEMINI_ONLY_FEATURES:
            if agent_meta.get(key):
                logger.warning(
                    "Feature '%s' is not supported by %s provider; ignoring",
                    key,
                    self.name,
                )

        # Load system instructions and rules
        system_instructions = self.load_system_prompt(root_dir)
        rules = self.load_rules(root_dir)

        # Construct system context
        system_context = self.construct_system_prompt(
            agent_persona,
            rules,
            system_instructions,
        )

        # Determine model
        model = model_override or agent_meta.get("model")
        if not model:
            tier = agent_meta.get("tier", "MEDIUM")
            model = self.get_best_model_for_capability(CapabilityLevel[tier.upper()])

        # Prepare environment
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env["VAULTSPEC_ROOT_DIR"] = str(root_dir)
        env["VAULTSPEC_AGENT_MODE"] = mode
        if system_context:
            env["VAULTSPEC_SYSTEM_PROMPT"] = system_context

        # Safety & control features from agent YAML
        if agent_meta.get("max_turns"):
            env["VAULTSPEC_MAX_TURNS"] = agent_meta["max_turns"]
        if agent_meta.get("budget"):
            env["VAULTSPEC_BUDGET_USD"] = agent_meta["budget"]
        if agent_meta.get("allowed_tools"):
            env["VAULTSPEC_ALLOWED_TOOLS"] = agent_meta["allowed_tools"]
        if agent_meta.get("disallowed_tools"):
            env["VAULTSPEC_DISALLOWED_TOOLS"] = agent_meta["disallowed_tools"]
        if agent_meta.get("effort"):
            env["VAULTSPEC_EFFORT"] = agent_meta["effort"]
        if agent_meta.get("output_format"):
            env["VAULTSPEC_OUTPUT_FORMAT"] = agent_meta["output_format"]
        if agent_meta.get("fallback_model"):
            env["VAULTSPEC_FALLBACK_MODEL"] = agent_meta["fallback_model"]
        include_dirs = agent_meta.get("include_dirs", "")
        if include_dirs:
            validated = self._validate_include_dirs(include_dirs, root_dir)
            if validated:
                env["VAULTSPEC_INCLUDE_DIRS"] = ",".join(validated)

        return ProcessSpec(
            executable=sys.executable,
            args=[
                "-m",
                "protocol.acp.claude_bridge",
                "--model",
                model,
            ],
            env=env,
            cleanup_paths=[],
            initial_prompt_override=task_context,
            session_meta={"model": model},
        )
