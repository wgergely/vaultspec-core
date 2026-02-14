from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from .base import (
    AgentProvider,
    CapabilityLevel,
    GeminiModels,
    ProcessSpec,
    resolve_includes,
)

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
    def supported_models(self) -> list[str]:
        return GeminiModels.ALL

    def get_model_capability(self, model: str) -> CapabilityLevel:
        if "pro" in model:
            return CapabilityLevel.HIGH
        if "2.5-flash" in model:
            return CapabilityLevel.LOW
        return CapabilityLevel.MEDIUM

    def get_best_model_for_capability(self, level: CapabilityLevel) -> str:
        if level >= CapabilityLevel.HIGH:
            return GeminiModels.HIGH
        if level <= CapabilityLevel.LOW:
            return GeminiModels.LOW
        return GeminiModels.MEDIUM

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Loads and resolves nested rules from .gemini/rules/."""
        rules_dir = root_dir / ".gemini" / "rules"
        if not rules_dir.exists():
            return ""

        all_rules = []
        for rule_file in sorted(rules_dir.glob("*.md")):
            content = rule_file.read_text(encoding="utf-8")
            resolved = resolve_includes(content, root_dir, rules_dir)
            all_rules.append(resolved)

        return "\n\n".join(all_rules)

    def construct_system_prompt(self, persona: str, rules: str) -> str:
        """Combines persona and rules into a single system prompt."""
        return f"# AGENT PERSONA\n{persona}\n\n# SYSTEM RULES & CONTEXT\n{rules}"

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
    ) -> ProcessSpec:
        _ = agent_name
        _ = task_context
        #  Locate executable and check version
        executable = shutil.which("gemini") or "gemini"
        self.check_version(executable)

        #  Load and Mix Rules
        rules = self.load_rules(root_dir)
        system_prompt = self.construct_system_prompt(agent_persona, rules)

        #  Persist to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(system_prompt)
            temp_path = pathlib.Path(tf.name)

        #  Prepare Environment
        env = os.environ.copy()
        # Ensure Gemini CLI uses the project's CWD for its internal MCP lookups
        env["GEMINI_CWD"] = str(root_dir)

        #  Determine Model
        model = model_override or agent_meta.get("model")
        if not model:
            tier = agent_meta.get("tier", "MEDIUM")
            model = self.get_best_model_for_capability(CapabilityLevel[tier.upper()])

        #  Build Args
        args = ["--experimental-acp", "--system", str(temp_path), "--model", model]

        return ProcessSpec(
            executable=executable,
            args=args,
            env=env,
            cleanup_paths=[temp_path],
        )
