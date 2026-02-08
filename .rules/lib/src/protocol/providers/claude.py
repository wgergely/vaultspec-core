from __future__ import annotations

import os
import pathlib
import shutil
import sys
from typing import Dict, List, Optional, Tuple

from .base import AgentProvider, ProcessSpec, CapabilityLevel, resolve_includes

class ClaudeProvider(AgentProvider):
    """Claude-based agent provider using @zed-industries/claude-code-acp."""

    @property
    def name(self) -> str:
        return "claude"

    @property
    def supported_models(self) -> List[str]:
        return [
            "claude-opus-4-6",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
        ]

    def get_model_capability(self, model: str) -> CapabilityLevel:
        if "haiku" in model:
            return CapabilityLevel.LOW
        if "sonnet" in model:
            return CapabilityLevel.MEDIUM
        if "opus" in model:
            return CapabilityLevel.HIGH

        # Default
        return CapabilityLevel.MEDIUM

    def get_best_model_for_capability(self, level: CapabilityLevel) -> str:
        if level == CapabilityLevel.LOW:
            return "claude-haiku-4-5"
        if level == CapabilityLevel.MEDIUM:
            return "claude-sonnet-4-5"
        if level == CapabilityLevel.HIGH:
            return "claude-opus-4-6"
        return "claude-sonnet-4-5"

    def resolve_includes(self, content: str, base_dir: pathlib.Path, root_dir: pathlib.Path) -> str:
        """Delegates to the shared resolve_includes utility."""
        return resolve_includes(content, base_dir, root_dir)

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Loads system rules from CLAUDE.md and recursively resolves all includes."""
        claude_dir = root_dir / ".claude"
        claude_config = claude_dir / "CLAUDE.md"

        if not claude_config.exists():
            return ""

        resolved_path = claude_config.resolve()
        if not resolved_path.is_relative_to(root_dir):
             return ""

        content = resolved_path.read_text(encoding="utf-8")
        return self.resolve_includes(content, claude_dir, root_dir)

    def construct_system_prompt(self, persona: str, rules: str) -> str:
        prompt = f"# AGENT PERSONA
{persona}

# SYSTEM RULES & CONTEXT
{rules}"
        # print(f"[DEBUG] System Prompt:
{prompt}", file=sys.stderr)
        return prompt

    def prepare_process(
        self, 
        agent_name: str, 
        agent_meta: Dict[str, str], 
        agent_persona: str, 
        task_context: str,
        root_dir: pathlib.Path,
        model_override: Optional[str] = None
    ) -> ProcessSpec:
        
        # 1. Load and Mix Rules (Same as Gemini)
        rules = self.load_rules(root_dir)
        system_prompt = self.construct_system_prompt(agent_persona, rules)

        # 2. Prepare Environment
        env = os.environ.copy()
        
        # 3. Construct Command
        # Use npx to run the adapter
        executable = shutil.which("npx")
        if not executable:
            # Fallback for Windows if npx not in path directly but npx.cmd is
            executable = shutil.which("npx.cmd")
        
        if not executable:
             raise RuntimeError("npx not found. Please ensure Node.js and npm are installed.")

        cmd_args = ["-y", "@zed-industries/claude-code-acp"]
        
        # TODO: investigate - Although model is selected via provider matching, we can pass it to the adapter
        # if the adapter supported it via args, but looking at source, it reads settings.
        # However, ACP has setSessionModel support.
        # But wait, acp-agent.ts checks `params._meta?.claudeCode?.options`
        # and `settings.model`.
        # We can pass model preference if we wanted, but acp_dispatch is responsible for
        # selecting the provider. Inside the session, `claude-code` manages its own model config.
        # But we can try to hint it if we want.
        # For now, let's stick to just launching the adapter.
        
        # 4. Session Metadata for System Prompt
        # TODO: investigate - We also prepend to the first message to ensure adherence (fallback strategy)
        initial_prompt = f"{system_prompt}

# TASK
{task_context}"
        
        session_meta = {
             "systemPrompt": system_prompt
        }

        return ProcessSpec(
            executable=executable,
            args=cmd_args,
            env=env,
            cleanup_paths=[],
            session_meta=session_meta,
            initial_prompt_override=initial_prompt
        )
