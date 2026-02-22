"""A2A (Agent-to-Agent) protocol support.

Provides agent cards, discovery, server, and state mapping.
"""

from .agent_card import agent_card_from_definition as agent_card_from_definition
from .discovery import generate_agent_md as generate_agent_md
from .discovery import write_agent_discovery as write_agent_discovery
from .discovery import write_gemini_settings as write_gemini_settings
from .server import create_app as create_app
from .state_map import A2A_TO_VAULTSPEC as A2A_TO_VAULTSPEC
from .state_map import VAULTSPEC_TO_A2A as VAULTSPEC_TO_A2A
