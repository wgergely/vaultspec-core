"""Public surface for vaultspec resource management and sync orchestration.

Aggregates per-resource CRUD (:func:`agents_add`, :func:`rules_sync`,
:func:`skills_list`, :func:`system_sync`), the sync engine
(:func:`sync_files`, :func:`format_summary`), config generation
(:func:`config_show`, :func:`config_sync`), I/O helpers
(:func:`atomic_write`, :func:`build_file`), domain exceptions
(:class:`VaultSpecError` and subclasses), and path/type contracts
(:class:`SyncResult`, :class:`ToolConfig`, :class:`WorkspaceContext`).
Consumed by :mod:`vaultspec_core.cli` and :mod:`vaultspec_core.mcp_server`.
"""

from .agents import agents_add as agents_add
from .agents import agents_list as agents_list
from .agents import agents_sync as agents_sync
from .agents import collect_agents as collect_agents
from .agents import transform_agent as transform_agent
from .config_gen import config_show as config_show
from .config_gen import config_sync as config_sync
from .exceptions import ProviderError as ProviderError
from .exceptions import ProviderNotInstalledError as ProviderNotInstalledError
from .exceptions import ResourceExistsError as ResourceExistsError
from .exceptions import ResourceNotFoundError as ResourceNotFoundError
from .exceptions import VaultSpecError as VaultSpecError
from .exceptions import WorkspaceNotInitializedError as WorkspaceNotInitializedError
from .helpers import atomic_write as atomic_write
from .helpers import build_file as build_file
from .helpers import ensure_dir as ensure_dir
from .mcps import collect_mcp_servers as collect_mcp_servers
from .mcps import mcp_add as mcp_add
from .mcps import mcp_list as mcp_list
from .mcps import mcp_remove as mcp_remove
from .mcps import mcp_sync as mcp_sync
from .resources import resource_edit as resource_edit
from .resources import resource_remove as resource_remove
from .resources import resource_rename as resource_rename
from .resources import resource_show as resource_show
from .rules import collect_rules as collect_rules
from .rules import rules_add as rules_add
from .rules import rules_list as rules_list
from .rules import rules_sync as rules_sync
from .rules import transform_rule as transform_rule
from .skills import collect_skills as collect_skills
from .skills import skills_add as skills_add
from .skills import skills_list as skills_list
from .skills import skills_sync as skills_sync
from .skills import transform_skill as transform_skill
from .sync import format_summary as format_summary
from .sync import sync_files as sync_files
from .system import system_show as system_show
from .system import system_sync as system_sync
from .types import CONFIG_HEADER as CONFIG_HEADER
from .types import SyncResult as SyncResult
from .types import ToolConfig as ToolConfig
from .types import WorkspaceContext as WorkspaceContext
from .types import get_context as get_context
from .types import init_paths as init_paths
from .types import set_context as set_context
