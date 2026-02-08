from __future__ import annotations

import logging
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

from .base import AgentProvider, ProcessSpec, CapabilityLevel, resolve_includes, load_mcp_servers

logger = logging.getLogger(__name__)

# Minimum versions for Gemini CLI ACP support
_MIN_VERSION_WINDOWS = (0, 9, 0)   # v0.9.0 fixes Windows ACP hang
_MIN_VERSION_RECOMMENDED = (0, 27, 0)  # v0.27.0 has stable agent skills

# Cache for version check result
_cached_version: Optional[Tuple[int, ...]] = None

SUPPORTED_MODELS = [
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]

class GeminiProvider(AgentProvider):
    """Gemini-based agent provider."""

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def supported_models(self) -> List[str]:
        return [
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ]

    def get_model_capability(self, model: str) -> CapabilityLevel:
        if "3-pro" in model:
            return CapabilityLevel.HIGH
        if "3-flash" in model:
            return CapabilityLevel.MEDIUM
        if "2.5-pro" in model:
            return CapabilityLevel.MEDIUM
        if "2.5-flash" in model:
            return CapabilityLevel.LOW
        if "flash" in model:
            return CapabilityLevel.LOW
        return CapabilityLevel.MEDIUM

    def get_best_model_for_capability(self, level: CapabilityLevel) -> str:
        if level == CapabilityLevel.LOW:
            return "gemini-2.5-flash"
        if level == CapabilityLevel.MEDIUM:
            return "gemini-3-flash-preview"
        if level == CapabilityLevel.HIGH:
            return "gemini-3-pro-preview"
        return "gemini-3-flash-preview"

    def resolve_includes(self, content: str, base_dir: pathlib.Path, root_dir: pathlib.Path) -> str:
        """Delegates to the shared resolve_includes utility."""
        return resolve_includes(content, base_dir, root_dir)

    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Loads system rules from GEMINI.md and recursively resolves all includes."""
        gemini_dir = root_dir / ".gemini"
        gemini_config = gemini_dir / "GEMINI.md"
        
        if not gemini_config.exists():
            return ""
        
        # Safe read manual check
        resolved_path = gemini_config.resolve()
        if not resolved_path.is_relative_to(root_dir):
             return ""
        
        content = resolved_path.read_text(encoding="utf-8")
        return self.resolve_includes(content, gemini_dir, root_dir)

    def construct_system_prompt(self, persona: str, rules: str) -> str:
        return f"# AGENT PERSONA
{persona}

# SYSTEM RULES & CONTEXT
{rules}"

    @staticmethod
    def check_version(executable: str) -> Optional[Tuple[int, ...]]:
        """Check Gemini CLI version and warn/fail based on known-good baselines.

        Returns the parsed version tuple or None if version could not be determined.
        Results are cached to avoid repeated subprocess calls.
        """
        global _cached_version
        if _cached_version is not None:
            return _cached_version

        try:
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout.strip() or result.stderr.strip()
            # Parse version from output like "Gemini CLI v0.27.0" or "0.27.0"
            match = re.search(r"(\d+)\.(\d+)\.(\d+)", output)
            if not match:
                logger.warning("Could not parse Gemini CLI version from: %s", output)
                return None

            version = tuple(int(x) for x in match.groups())
            _cached_version = version

            if sys.platform == "win32" and version < _MIN_VERSION_WINDOWS:
                raise RuntimeError(
                    f"Gemini CLI v{'.'.join(str(x) for x in version)} is below minimum "
                    f"v{'.'.join(str(x) for x in _MIN_VERSION_WINDOWS)} required on Windows "
                    f"(ACP hang bug). Please upgrade: npm install -g @anthropic-ai/gemini-cli"
                )

            if version < _MIN_VERSION_RECOMMENDED:
                logger.warning(
                    "Gemini CLI v%s is below recommended v%s. "
                    "Some features may not work correctly.",
                    ".".join(str(x) for x in version),
                    ".".join(str(x) for x in _MIN_VERSION_RECOMMENDED),
                )

            return version
        except FileNotFoundError:
            logger.warning("Gemini CLI executable not found: %s", executable)
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Gemini CLI version check timed out")
            return None

    def prepare_process(
        self,
        agent_name: str,
        agent_meta: Dict[str, str],
        agent_persona: str,
        task_context: str,
        root_dir: pathlib.Path,
        model_override: Optional[str] = None
    ) -> ProcessSpec:
        
        # 0. Locate executable and check version
        executable = shutil.which("gemini") or "gemini"
        self.check_version(executable)

        # 1. Load and Mix Rules
        rules = self.load_rules(root_dir)
        system_prompt = self.construct_system_prompt(agent_persona, rules)

        # 2. Persist to temp file
        tf = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tf.write(system_prompt)
        tf.close()
        temp_path = pathlib.Path(tf.name)

        # 3. Prepare Environment
        env = os.environ.copy()
        env["GEMINI_SYSTEM_MD"] = str(temp_path)

        # 4. Construct Command
        cmd_args = ["--experimental-acp"]

        target_model = model_override or agent_meta.get("model")
        if target_model:
            cmd_args.extend(["--model", target_model])

        # 5. Load MCP servers from .gemini/settings.json
        mcp_servers = load_mcp_servers(root_dir)

        # 6. TODO: investigate - Dual delivery: env var + prompt prepend as fallback
        initial_prompt = f"{system_prompt}

# TASK
{task_context}"

        return ProcessSpec(
            executable=executable,
            args=cmd_args,
            env=env,
            cleanup_paths=[temp_path],
            mcp_servers=mcp_servers,
            initial_prompt_override=initial_prompt,
        )
