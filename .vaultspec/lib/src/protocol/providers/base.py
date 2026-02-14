from __future__ import annotations

import abc
import json
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)


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


def load_mcp_servers(root_dir: pathlib.Path) -> list[dict[str, Any]]:
    """Load MCP server configurations from settings.json.

    Searches for settings.json in .gemini, .claude, or .agent directories.
    Reads the mcpServers block and converts each entry into the ACP
    McpServerConfig format.

    Returns an empty list if no settings file is found or if it's malformed.
    """
    search_paths = [
        root_dir / ".gemini" / "settings.json",
        root_dir / ".claude" / "settings.json",
        root_dir / ".agent" / "settings.json",
    ]

    settings_path = None
    for path in search_paths:
        if path.exists():
            settings_path = path
            break

    if not settings_path:
        return []

    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Failed to read settings file {settings_path}: {exc}")
        return []

    mcp_block = data.get("mcpServers")
    if not isinstance(mcp_block, dict):
        return []

    servers: list[dict[str, Any]] = []
    for name, cfg in mcp_block.items():
        if not isinstance(cfg, dict) or "command" not in cfg:
            logger.warning(f"Skipping malformed MCP server entry: {name}")
            continue
        servers.append(
            {
                "name": name,
                "command": cfg["command"],
                "args": cfg.get("args", []),
                "env": cfg.get("env", {}),
            }
        )

    return servers


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

    @property
    def supported_models(self) -> list[str]:
        return self.models.ALL

    def get_model_capability(self, model: str) -> CapabilityLevel:
        """Look up capability level from the registry. Defaults to MEDIUM."""
        for level, name in self.models.BY_LEVEL.items():
            if name == model:
                return level
        return CapabilityLevel.MEDIUM

    def get_best_model_for_capability(self, level: CapabilityLevel) -> str:
        """Look up best model from the registry. Defaults to MEDIUM."""
        return self.models.BY_LEVEL.get(level, self.models.MEDIUM)

    @abc.abstractmethod
    def prepare_process(
        self,
        agent_name: str,
        agent_meta: dict[str, str],
        agent_persona: str,
        task_context: str,
        root_dir: pathlib.Path,
        model_override: str | None = None,
    ) -> ProcessSpec:
        """Prepares the process specification for spawning the agent.

        Args:
            agent_name: Name of the agent.
            agent_meta: Metadata dictionary from the agent definition.
            agent_persona: The persona/instructions for the agent.
            task_context: The initial task description.
            root_dir: The workspace root directory.
            model_override: Optional model override.

        Returns:
            ProcessSpec containing command, args, env, cleanup paths,
            and session metadata.
        """
        pass
