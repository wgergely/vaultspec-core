from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import uuid
from typing import TYPE_CHECKING, Any

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
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Features only supported by the Claude provider
_CLAUDE_ONLY_FEATURES = (
    "max_turns",
    "budget",
    "disallowed_tools",
    "effort",
    "fallback_model",
)

_MIN_VERSION_WINDOWS = (0, 9, 0)  # v0.9.0 fixes Windows ACP hang
_MIN_VERSION_RECOMMENDED = (0, 27, 0)  # v0.27.0 has stable agent skills

# Cache for version check result
_cached_version: tuple[int, ...] | None = None

# Overridable which function for testing
_which_fn: Callable[[str], str | None] = shutil.which


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

    @staticmethod
    def check_version(
        executable: str, *, run_fn: Callable[..., Any] | None = None
    ) -> tuple[int, ...] | None:
        """Check Gemini CLI version and warn/fail based on known-good baselines.

        Returns the parsed version tuple or None if version could not be determined.
        Pass ``run_fn`` to inject a replacement for ``subprocess.run`` (testing).
        """
        global _cached_version
        if _cached_version:
            return _cached_version

        _run = run_fn or subprocess.run
        try:
            res = _run(
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

        # Warn on Claude-only features
        for key in _CLAUDE_ONLY_FEATURES:
            if agent_meta.get(key):
                logger.warning(
                    "Feature '%s' is not supported by %s provider; ignoring",
                    key,
                    self.name,
                )

        #  Locate executable and check version
        executable = _which_fn("gemini") or "gemini"
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
        cleanup_paths: list[pathlib.Path] = []

        # Write system prompt to temp file for GEMINI_SYSTEM_MD
        if system_prompt:
            tmp_dir = root_dir / ".vaultspec" / ".tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            system_file = tmp_dir / f"system-{uuid.uuid4().hex[:8]}.md"
            system_file.write_text(system_prompt, encoding="utf-8")
            env["GEMINI_SYSTEM_MD"] = str(system_file)
            cleanup_paths.append(system_file)

        #  Determine Model
        model = model_override or agent_meta.get("model")
        if not model:
            tier = agent_meta.get("tier", "MEDIUM")
            model = self.get_best_model_for_capability(CapabilityLevel[tier.upper()])

        #  Build Args (Gemini CLI has no --system flag)
        args = ["--experimental-acp", "--model", model]
        if mode == "read-only":
            args.append("--sandbox")

        # Tool control
        allowed = agent_meta.get("allowed_tools", "")
        if allowed:
            for tool in (t.strip() for t in allowed.split(",") if t.strip()):
                args.extend(["--allowed-tools", tool])

        # Approval mode (Gemini-specific: default|auto_edit|yolo|plan)
        approval = agent_meta.get("approval_mode")
        if approval and approval != "default":
            args.extend(["--approval-mode", approval])

        # Output format (text|json|stream-json)
        fmt = agent_meta.get("output_format")
        if fmt and fmt != "text":
            args.extend(["--output-format", fmt])

        # Additional workspace directories (validated against traversal)
        include_dirs = agent_meta.get("include_dirs", "")
        if include_dirs:
            for d in self._validate_include_dirs(include_dirs, root_dir):
                args.extend(["--include-directories", d])

        return ProcessSpec(
            executable=executable,
            args=args,
            env=env,
            cleanup_paths=cleanup_paths,
            initial_prompt_override=task_context,
        )
