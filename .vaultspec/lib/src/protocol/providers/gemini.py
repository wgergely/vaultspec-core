from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

from .base import (
    AgentProvider,
    CapabilityLevel,
    GeminiModels,
    ModelRegistry,
    ProcessSpec,
    resolve_includes,
)

if TYPE_CHECKING:
    import pathlib

_MIN_VERSION_WINDOWS = (0, 9, 0)  # v0.9.0 fixes Windows ACP hang
_MIN_VERSION_RECOMMENDED = (0, 27, 0)  # v0.27.0 has stable agent skills

# Cache for version check result
_cached_version: tuple[int, ...] | None = None


class GeminiProvider(AgentProvider):
    """Provider for Google Gemini models via Gemini CLI."""

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def models(self) -> ModelRegistry:
        return GeminiModels

    def load_system_prompt(self, root_dir: pathlib.Path) -> str:
        """Loads .gemini/SYSTEM.md if it exists (deployed by CLI sync)."""
        system_file = root_dir / ".gemini" / "SYSTEM.md"
        if not system_file.exists():
            return ""
        return system_file.read_text(encoding="utf-8")

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Loads and resolves nested rules from .gemini/rules/."""
        rules_dir = root_dir / ".gemini" / "rules"
        if not rules_dir.exists():
            return ""

        all_rules = []
        for rule_file in sorted(rules_dir.glob("*.md")):
            content = rule_file.read_text(encoding="utf-8")
            resolved = resolve_includes(content, rules_dir, root_dir)
            all_rules.append(resolved)

        return "\n\n".join(all_rules)

    def construct_system_prompt(
        self,
        persona: str,
        rules: str,
        system_instructions: str = "",
    ) -> str:
        """Combines system instructions, persona, and rules."""
        parts = []
        if system_instructions.strip():
            parts.append(f"# SYSTEM INSTRUCTIONS\n{system_instructions}")
        if persona.strip():
            parts.append(f"# AGENT PERSONA\n{persona}")
        if rules.strip():
            parts.append(f"# SYSTEM RULES & CONTEXT\n{rules}")
        return "\n\n".join(parts)

    @staticmethod
    def check_version(executable: str) -> tuple[int, ...] | None:
        """Check Gemini CLI version and warn/fail based on known-good baselines.

        Returns the parsed version tuple or None if version could not be determined.
        """
        global _cached_version
        if _cached_version:
            return _cached_version

        try:
            res = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            # Match "gemini v0.27.0" or just "v0.27.0"
            match = re.search(r"v(\d+)\.(\d+)\.(\d+)", res.stdout)
            if not match:
                return None

            version = tuple(int(x) for x in match.groups())
            _cached_version = version

            # Enforcement
            if sys.platform == "win32" and version < _MIN_VERSION_WINDOWS:
                msg = (
                    f"Gemini CLI version {version} is below minimum "
                    f"{_MIN_VERSION_WINDOWS} for Windows."
                )
                raise RuntimeError(msg)

            return version
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            return None

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

        #  Locate executable and check version
        executable = shutil.which("gemini") or "gemini"
        self.check_version(executable)

        #  Load system instructions, rules, and construct full prompt
        system_instructions = self.load_system_prompt(root_dir)
        rules = self.load_rules(root_dir)
        system_prompt = self.construct_system_prompt(
            agent_persona,
            rules,
            system_instructions,
        )

        #  Prepare Environment
        env = os.environ.copy()
        # Ensure Gemini CLI uses the project's CWD for its internal MCP lookups
        env["GEMINI_CWD"] = str(root_dir)

        #  Determine Model
        model = model_override or agent_meta.get("model")
        if not model:
            tier = agent_meta.get("tier", "MEDIUM")
            model = self.get_best_model_for_capability(CapabilityLevel[tier.upper()])

        #  Build Args (Gemini CLI has no --system flag)
        args = ["--experimental-acp", "--model", model]
        if mode == "read-only":
            args.append("--sandbox")

        # Prepend system prompt to initial task via initial_prompt_override
        initial_prompt = (
            f"{system_prompt}\n\n# TASK\n{task_context}"
            if system_prompt
            else task_context
        )

        return ProcessSpec(
            executable=executable,
            args=args,
            env=env,
            cleanup_paths=[],
            initial_prompt_override=initial_prompt,
        )
