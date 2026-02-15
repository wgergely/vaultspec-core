"""Generate Gemini CLI agent discovery configuration.

Gemini CLI discovers A2A agents via markdown files in ``.gemini/agents/``
and ``settings.json`` with experimental agent support enabled.

See: https://a2a-protocol.org/latest/ for discovery spec.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


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
    host: str = "localhost",
    port: int = 10010,
    description: str = "",
) -> Path:
    """Write a Gemini CLI agent discovery file to ``.gemini/agents/``.

    Creates the directory structure if it doesn't exist.

    Returns:
        Path to the created markdown file.
    """
    agents_dir = root_dir / ".gemini" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    card_url = f"http://{host}:{port}/.well-known/agent.json"
    content = generate_agent_md(agent_name, card_url, description)

    md_path = agents_dir / f"{agent_name}.md"
    md_path.write_text(content, encoding="utf-8")
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
    settings_dir = root_dir / ".gemini"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / "settings.json"

    settings: dict = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))

    settings.setdefault("experimental", {})
    settings["experimental"]["enableAgents"] = enable_agents

    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return settings_path
