"""Abstract base classes and shared utilities for agent provider implementations."""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)

__all__ = [
    "AgentProvider",
    "CapabilityLevel",
    "ClaudeModels",
    "GeminiModels",
    "ModelRegistry",
    "ProcessSpec",
    "resolve_executable",
    "resolve_includes",
]


class CapabilityLevel(IntEnum):
    """Tiered capability levels used to select an appropriate model."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


class ClaudeModels:
    """Single source of truth for Claude model identifiers.

    Attributes:
        HIGH: Model ID for the highest capability tier (Opus).
        MEDIUM: Model ID for the medium capability tier (Sonnet).
        LOW: Model ID for the low capability tier (Haiku).
        ALL: All model IDs ordered from highest to lowest capability.
        BY_LEVEL: Mapping from CapabilityLevel to model ID.
    """

    HIGH = "claude-opus-4-6"
    MEDIUM = "claude-sonnet-4-6"
    LOW = "claude-haiku-4-5"

    ALL: ClassVar[list[str]] = [HIGH, MEDIUM, LOW]

    BY_LEVEL: ClassVar[dict[CapabilityLevel, str]] = {
        CapabilityLevel.HIGH: HIGH,
        CapabilityLevel.MEDIUM: MEDIUM,
        CapabilityLevel.LOW: LOW,
    }


class GeminiModels:
    """Single source of truth for Gemini model identifiers.

    Attributes:
        HIGH: Model ID for the highest capability tier (Pro).
        MEDIUM: Model ID for the medium capability tier (Flash).
        LOW: Model ID for the low capability tier (Flash 2.5).
        ALL: All model IDs ordered from highest to lowest capability.
        BY_LEVEL: Mapping from CapabilityLevel to model ID.
    """

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
    """Specification for launching an agent subprocess.

    Attributes:
        executable: Path or name of the executable to run.
        args: Command-line arguments to pass to the executable.
        env: Full environment dictionary for the subprocess.
        cleanup_paths: Temporary files to delete after the process exits.
        session_meta: Arbitrary metadata to attach to the session record
            (e.g., model name used).
        initial_prompt_override: If set, replaces the task context passed
            as the first user message.
        mcp_servers: MCP server configurations to expose to the agent.
    """

    executable: str
    args: list[str]
    env: dict[str, str]
    cleanup_paths: list[pathlib.Path]
    session_meta: dict[str, Any] = field(default_factory=dict)
    initial_prompt_override: str | None = None
    mcp_servers: dict[str, Any] | None = None


def resolve_includes(
    content: str, base_dir: pathlib.Path, root_dir: pathlib.Path
) -> str:
    """Recursively resolve ``@path/to/file.md`` includes within Markdown content.

    Lines beginning with ``@`` are treated as include directives. Paths are
    resolved relative to ``base_dir`` first, then relative to ``root_dir``
    as a fallback. Resolved paths must remain inside ``root_dir`` to prevent
    path-traversal reads.

    Args:
        content: Markdown source text that may contain ``@include`` lines.
        base_dir: Directory of the file being processed (used for relative
            resolution first).
        root_dir: Workspace root used as the fallback resolution base and as
            the security boundary.

    Returns:
        Markdown string with all include directives replaced by the content
        of the referenced files, wrapped in HTML comments indicating the
        source path. Missing or out-of-bounds includes are replaced with
        an HTML error comment.
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
            logger.warning(
                "Include resolution failed: %s — path not found",
                include_path_str,
            )
            resolved_lines.append(
                f"<!-- ERROR: Missing include: {include_path_str} -->"
            )
            continue

        try:
            if not include_path.is_relative_to(resolved_root):
                logger.warning(
                    "Include resolution failed: %s — path outside workspace",
                    include_path_str,
                )
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
            logger.warning("Include resolution failed: %s — %s", include_path_str, e)
            resolved_lines.append(f"<!-- ERROR: Include failed: {e} -->")

    return "\n".join(resolved_lines)


def resolve_executable(name: str, which_fn=None) -> tuple[str, list[str]]:
    """Resolve an executable name, handling Windows .cmd/.bat wrappers.

    On Windows, tools installed via npm/uv often appear as .cmd batch
    scripts that cannot be directly launched by subprocess or
    asyncio.create_subprocess_exec. This function wraps them with
    ``cmd.exe /c`` so they execute correctly.

    Args:
        name: Executable name to resolve (e.g. ``"gemini"``).
        which_fn: Optional replacement for ``shutil.which`` (injectable for
            testing).

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
        """Return the model ID that best matches the requested capability level.

        Args:
            level: Desired capability tier.

        Returns:
            Model ID string; falls back to the MEDIUM model when the level
            is not found in the registry.
        """
        return self.models.BY_LEVEL.get(level, self.models.MEDIUM)

    @abc.abstractmethod
    def load_system_prompt(self, root_dir: pathlib.Path) -> str:
        """Load the provider-specific top-level system prompt file.

        Args:
            root_dir: Workspace root directory.

        Returns:
            System prompt text, or an empty string if no file exists.
        """

    @abc.abstractmethod
    def load_rules(self, root_dir: pathlib.Path) -> str:
        """Load and inline-resolve provider-specific rules files.

        Args:
            root_dir: Workspace root directory.

        Returns:
            Concatenated rules text with all ``@include`` directives resolved,
            or an empty string if no rules directory exists.
        """

    def construct_system_prompt(
        self,
        persona: str,
        rules: str,
        system_instructions: str = "",
    ) -> str:
        """Build a combined system prompt from instructions, persona, and rules.

        Sections are labelled with Markdown headings and joined with blank
        lines. Empty sections are omitted.

        Args:
            persona: Agent persona / behavioural instructions.
            rules: Pre-resolved rules text.
            system_instructions: Optional global system instructions to
                prepend before the persona section.

        Returns:
            Combined system prompt string, or an empty string when all inputs
            are blank.
        """
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
        """Validate a comma-separated list of include directories for path traversal.

        Each directory is resolved relative to ``root_dir`` and kept only if the
        resolved path stays within ``root_dir``.

        Args:
            include_dirs: Comma-separated directory paths (relative to root).
            root_dir: Workspace root used as the security boundary.

        Returns:
            List of validated directory strings that are safe to pass to the agent.
        """
        validated: list[str] = []
        for d in (x.strip() for x in include_dirs.split(",") if x.strip()):
            try:
                resolved = (root_dir / d).resolve()
                if resolved.is_relative_to(root_dir.resolve()):
                    validated.append(d)
                else:
                    logger.warning(
                        "include_dirs path '%s' rejected: outside workspace root",
                        d,
                    )
            except (ValueError, OSError) as exc:
                logger.warning("include_dirs path '%s' rejected: %s", d, exc)
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
        mcp_servers: dict[str, Any] | None = None,
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
