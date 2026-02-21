"""A2A (Agent-to-Agent) protocol support."""

from .agent_card import agent_card_from_definition
from .discovery import generate_agent_md, write_agent_discovery, write_gemini_settings
from .server import create_app
from .state_map import A2A_TO_VAULTSPEC, VAULTSPEC_TO_A2A

__all__ = [
    "A2A_TO_VAULTSPEC",
    "VAULTSPEC_TO_A2A",
    "agent_card_from_definition",
    "create_app",
    "generate_agent_md",
    "write_agent_discovery",
    "write_gemini_settings",
]
