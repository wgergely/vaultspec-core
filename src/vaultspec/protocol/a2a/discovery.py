"""Generate Gemini CLI agent discovery configuration.

Gemini CLI discovers A2A agents via markdown files in ``.gemini/agents/``
and ``settings.json`` with experimental agent support enabled.

See: https://a2a-protocol.org/latest/ for discovery spec.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["generate_agent_md", "write_agent_discovery", "write_gemini_settings"]


def generate_agent_md(
    agent_name: str,
    agent_card_url: str,
    description: str = "",
) -> str:
    """Generate a Gemini CLI agent discovery markdown file.

    Args:
        agent_name: Name of the agent.
        agent_card_url: URL to the agent's A2A agent card
                        (e.g., ``http://localhost:10010/.well-known/agent.json``).
        description: Optional description of the agent.

    Returns:
        Markdown string for ``.gemini/agents/<name>.md``.
    """
    lines = [
        f"# {agent_name}",
        "",
        description or f"Vaultspec {agent_name} agent via A2A protocol.",
        "",
        f"agent_card_url: {agent_card_url}",
    ]
    return "\n".join(lines) + "\n"


def write_agent_discovery(
    root_dir: Path,
    agent_name: str,
    host: str | None = None,
    port: int | None = None,
    description: str = "",
) -> Path:
    """Write a Gemini CLI agent discovery file to ``.gemini/agents/``.

    Creates the directory structure if it doesn't exist.

    Returns:
        Path to the created markdown file.
    """
    from vaultspec.core import get_config

    logger.info("Writing agent discovery for %s to %s", agent_name, root_dir)

    cfg = get_config()
    host = host or cfg.a2a_host
    port = port or cfg.a2a_default_port

    agents_dir = root_dir / ".gemini" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("Created agents directory: %s", agents_dir)

    card_url = f"http://{host}:{port}/.well-known/agent.json"
    content = generate_agent_md(agent_name, card_url, description)

    md_path = agents_dir / f"{agent_name}.md"
    md_path.write_text(content, encoding="utf-8")
    logger.info("Agent discovery file written to %s", md_path)
    return md_path


def write_gemini_settings(
    root_dir: Path,
    enable_agents: bool = True,
) -> Path:
    """Write or update ``.gemini/settings.json`` with agent support.

    Preserves any existing keys in the settings file.

    Returns:
        Path to the settings file.
    """
    logger.info(
        "Updating Gemini settings at %s (enable_agents=%s)", root_dir, enable_agents
    )

    settings_dir = root_dir / ".gemini"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / "settings.json"

    settings: dict = {}
    if settings_path.exists():
        logger.debug("Loading existing settings from %s", settings_path)
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    else:
        logger.debug("Creating new settings file at %s", settings_path)

    settings.setdefault("experimental", {})
    settings["experimental"]["enableAgents"] = enable_agents

    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    logger.info("Gemini settings written to %s", settings_path)
    return settings_path
