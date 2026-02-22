"""Unified MCP server package for vaultspec.

Consolidates subagent dispatch tools, team coordination tools,
and the FastMCP server entry point into a single package.
"""

from .app import create_server as create_server
from .app import main as main
from .subagent_tools import cancel_task as cancel_task
from .subagent_tools import dispatch_agent as dispatch_agent
from .subagent_tools import get_locks as get_locks
from .subagent_tools import get_task_status as get_task_status
from .subagent_tools import initialize_server as initialize_server
from .subagent_tools import list_agents as list_agents
from .subagent_tools import register_tools as register_subagent_tools
from .subagent_tools import subagent_lifespan as subagent_lifespan
from .team_tools import register_tools as register_team_tools
from .team_tools import set_root_dir as set_team_root_dir

__all__ = [
    "cancel_task",
    "create_server",
    "dispatch_agent",
    "get_locks",
    "get_task_status",
    "initialize_server",
    "list_agents",
    "main",
    "register_subagent_tools",
    "register_team_tools",
    "set_team_root_dir",
    "subagent_lifespan",
]
