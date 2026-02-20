from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import pathlib


class CapabilityLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class ClaudeModels:
    """Single source of truth for Claude model identifiers."""

    HIGH = "claude-opus-4-6"
    MEDIUM = "claude-sonnet-4-5"
    LOW = "claude-haiku-4-5"

    ALL: ClassVar[list[str]] = [HIGH, MEDIUM, LOW]

    BY_LEVEL: ClassVar[dict[CapabilityLevel, str]] = {
        CapabilityLevel.HIGH: HIGH,
        CapabilityLevel.MEDIUM: MEDIUM,
        CapabilityLevel.LOW: LOW,
    }


class GeminiModels:
    """Single source of truth for Gemini model identifiers."""

    HIGH = "gemini-3-pro-preview"
    MEDIUM = "gemini-3-flash-preview"
    LOW = "gemini-2.5-flash"

    ALL: ClassVar[list[str]] = [HIGH, MEDIUM, LOW]

    BY_LEVEL: ClassVar[dict[CapabilityLevel, str]] = {
        CapabilityLevel.HIGH: HIGH,
        CapabilityLevel.MEDIUM: MEDIUM,
        CapabilityLevel.LOW: LOW,
    }


# Type alias for model registry classes
ModelRegistry = type[ClaudeModels] | type[GeminiModels]


@dataclass
class ProcessSpec:
    """Specification for launching an agent process."""

    executable: str
    args: list[str]
    env: dict[str, str]
    cleanup_paths: list[pathlib.Path]
    session_meta: dict[str, Any] = field(default_factory=dict)
    initial_prompt_override: str | None = None
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)


def resolve_includes(
    content: str, base_dir: pathlib.Path, root_dir: pathlib.Path
) -> str:
    """Recursively resolves @path/to/file.md includes within markdown content.

    Resolution strategy:
       Try resolving relative to base_dir (directory of the including file)
       Fall back to resolving relative to root_dir (workspace root)
       Security: resolved path must be within root_dir
    """
    resolved_root = root_dir.resolve()
    lines = content.split("\n")
    resolved_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("@"):
            resolved_lines.append(line)
            continue

        include_path_str = stripped[1:].strip()

        # Skip URLs
        if include_path_str.startswith(("http://", "https://")):
            resolved_lines.append(line)
            continue

        # Normalize backslashes for cross-platform compatibility
        normalized = include_path_str.replace("\\", "/")

        # Try base_dir first (relative to including file), then root_dir
        include_path = None
        candidate = (base_dir / normalized).resolve()
        if candidate.exists():
            include_path = candidate
        else:
            candidate = (root_dir / normalized).resolve()
            if candidate.exists():
                include_path = candidate

        if include_path is None:
            resolved_lines.append(
                f"<!-- ERROR: Missing include: {include_path_str} -->"
            )
            continue

        try:
            if not include_path.is_relative_to(resolved_root):
                resolved_lines.append(
                    f"<!-- ERROR: Path outside workspace: {include_path_str} -->"
                )
                continue

            included_content = include_path.read_text(encoding="utf-8")
            display_path = str(include_path.relative_to(resolved_root)).replace(
                "\\", "/"
            )
            resolved_lines.append(f"\n<!-- Included from {display_path} -->\n")
            resolved_lines.append(
                resolve_includes(included_content, include_path.parent, root_dir)
            )
            resolved_lines.append(f"\n<!-- End of {display_path} -->\n")
        except Exception as e:
            resolved_lines.append(f"<!-- ERROR: Include failed: {e} -->")

    return "\n".join(resolved_lines)


def resolve_executable(name: str, which_fn=None) -> tuple[str, list[str]]:
    """Resolve an executable name, handling Windows .cmd/.bat wrappers.

    On Windows, tools installed via npm/pip often appear as .cmd batch
    scripts that cannot be directly launched by subprocess or
    asyncio.create_subprocess_exec. This function wraps them with
    ``cmd.exe /c`` so they execute correctly.

    Returns:
        (executable, prefix_args) — prepend prefix_args to the command's
        argument list when constructing the subprocess call.
    """
    import shutil
    import sys

    _which = which_fn or shutil.which
    path = _which(name) or name

    if sys.platform == "win32" and path.lower().endswith((".cmd", ".bat")):
        return "cmd.exe", ["/c", path]
    return path, []


class AgentProvider(abc.ABC):
    """Abstract base class for agent providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """The name of the provider (e.g., 'gemini', 'claude')."""

    @property
    @abc.abstractmethod
    def models(self) -> ModelRegistry:
        """The model registry class for this provider."""

    def get_best_model_for_capability(self, level: CapabilityLevel) -> str:
        """Look up best model from the registry. Defaults to MEDIUM."""
        return self.models.BY_LEVEL.get(level, self.models.MEDIUM)

    @abc.abstractmethod
    def load_system_prompt(self, root_dir: pathlib.Path) -> str:
        """Load provider-specific system prompt file."""

    @abc.abstractmethod
    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Load and resolve provider-specific rules."""

    def construct_system_prompt(
        self,
        persona: str,
        rules: str,
        system_instructions: str = "",
    ) -> str:
        """Combine system instructions, persona, and rules."""
        parts = []
        if system_instructions.strip():
            parts.append(f"# SYSTEM INSTRUCTIONS\n{system_instructions}")
        if persona.strip():
            parts.append(f"# AGENT PERSONA\n{persona}")
        if rules.strip():
            parts.append(f"# SYSTEM RULES & CONTEXT\n{rules}")
        return "\n\n".join(parts)

    def _validate_include_dirs(
        self,
        include_dirs: str,
        root_dir: pathlib.Path,
    ) -> list[str]:
        """Validate and filter include_dirs against path traversal."""
        validated: list[str] = []
        for d in (x.strip() for x in include_dirs.split(",") if x.strip()):
            try:
                resolved = (root_dir / d).resolve()
                if resolved.is_relative_to(root_dir.resolve()):
                    validated.append(d)
            except (ValueError, OSError):
                pass
        return validated

    @abc.abstractmethod
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
        """Prepares the process specification for spawning the agent.

        Args:
            agent_name: Name of the agent.
            agent_meta: Metadata dictionary from the agent definition.
            agent_persona: The persona/instructions for the agent.
            task_context: The initial task description.
            root_dir: The workspace root directory.
            model_override: Optional model override.
            mode: Agent sandbox mode ("read-only" or "read-write").

        Returns:
            ProcessSpec containing command, args, env, cleanup paths,
            and session metadata.
        """
        pass
