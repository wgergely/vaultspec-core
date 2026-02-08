from __future__ import annotations

import abc
import json
import logging
import pathlib
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CapabilityLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class ProcessSpec:
    """Specification for launching an agent process."""

    executable: str
    args: List[str]
    env: Dict[str, str]
    cleanup_paths: List[pathlib.Path]
    session_meta: Dict[str, Any] = field(default_factory=dict)
    initial_prompt_override: Optional[str] = None
    mcp_servers: List[Dict[str, Any]] = field(default_factory=list)


def resolve_includes(
    content: str, base_dir: pathlib.Path, root_dir: pathlib.Path
) -> str:
    """Recursively resolves @path/to/file.md includes within markdown content.

    Resolution strategy:
      1. Try resolving relative to base_dir (directory of the including file)
      2. Fall back to resolving relative to root_dir (workspace root)
      3. Security: resolved path must be within root_dir
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


def load_mcp_servers(root_dir: pathlib.Path) -> List[Dict[str, Any]]:
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
        logger.warning("Failed to read settings file %s: %s", settings_path, exc)
        return []

    mcp_block = data.get("mcpServers")
    if not isinstance(mcp_block, dict):
        return []

    servers: List[Dict[str, Any]] = []
    for name, cfg in mcp_block.items():
        if not isinstance(cfg, dict) or "command" not in cfg:
            logger.warning("Skipping malformed MCP server entry: %s", name)
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
        pass

    @property
    @abc.abstractmethod
    def supported_models(self) -> List[str]:
        """List of models supported by this provider."""
        pass

    @abc.abstractmethod
    def get_model_capability(self, model: str) -> CapabilityLevel:
        """Returns the capability level of a specific model.

        Raises:
            ValueError: If model is not supported by this provider.
        """
        pass

    @abc.abstractmethod
    def get_best_model_for_capability(self, level: CapabilityLevel) -> str:
        """Returns the best matching model for the requested capability level."""
        pass

    @abc.abstractmethod
    def prepare_process(
        self,
        agent_name: str,
        agent_meta: Dict[str, str],
        agent_persona: str,
        task_context: str,
        root_dir: pathlib.Path,
        model_override: Optional[str] = None,
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
            ProcessSpec containing command, args, env, cleanup paths, and session metadata.
        """
        pass
