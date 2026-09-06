"""Public surface for vaultspec resource management and sync orchestration.

Aggregates per-resource CRUD (:func:`agents_add`, :func:`rules_sync`,
:func:`skills_list`, :func:`system_sync`), the sync engine
(:func:`sync_files`), config generation
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
from .editor import (
    EDITOR_PROGRAM_ALLOWLIST as EDITOR_PROGRAM_ALLOWLIST,
)
from .editor import (
    EditorValidationError as EditorValidationError,
)
from .editor import (
    validate_editor_command as validate_editor_command,
)
from .enums import InstallMode as InstallMode
from .enums import McpScope as McpScope
from .enums import McpTargetFormat as McpTargetFormat
from .enums import Tool as Tool
from .exceptions import (
    EditorCancellationError as EditorCancellationError,
)
from .exceptions import (
    EditorResolutionError as EditorResolutionError,
)
from .exceptions import (
    EditorSubprocessError as EditorSubprocessError,
)
from .exceptions import ProviderError as ProviderError
from .exceptions import ProviderNotInstalledError as ProviderNotInstalledError
from .exceptions import ResourceExistsError as ResourceExistsError
from .exceptions import ResourceNotFoundError as ResourceNotFoundError
from .exceptions import VaultSpecError as VaultSpecError
from .exceptions import WorkspaceNotInitializedError as WorkspaceNotInitializedError
from .helpers import atomic_write as atomic_write
from .helpers import build_file as build_file
from .helpers import dump_yaml as dump_yaml
from .helpers import ensure_dir as ensure_dir
from .home import CoreHomeLayout as CoreHomeLayout
from .home import ProcessRegistryDiagnosis as ProcessRegistryDiagnosis
from .home import ProcessRegistrySignal as ProcessRegistrySignal
from .home import core_home_layout as core_home_layout
from .home import diagnose_process_registry as diagnose_process_registry
from .hooks import hooks_add as hooks_add
from .hooks import hooks_edit as hooks_edit
from .hooks import hooks_remove as hooks_remove
from .hooks import hooks_rename as hooks_rename
from .hooks import hooks_show as hooks_show
from .hooks import hooks_status as hooks_status
from .hooks import hooks_sync as hooks_sync
from .local_config import (
    KNOWN_KEYS as KNOWN_KEYS,
)
from .local_config import (
    get_config_value as get_config_value,
)
from .local_config import (
    get_local_config_path as get_local_config_path,
)
from .local_config import (
    read_local_config as read_local_config,
)
from .local_config import (
    resolve_editor as resolve_editor,
)
from .local_config import (
    set_config_value as set_config_value,
)
from .local_config import (
    unset_config_value as unset_config_value,
)
from .local_config import (
    write_local_config as write_local_config,
)
from .mcps import collect_mcp_servers as collect_mcp_servers
from .mcps import mcp_add as mcp_add
from .mcps import mcp_list as mcp_list
from .mcps import mcp_remove as mcp_remove
from .mcps import mcp_status as mcp_status
from .mcps import mcp_sync as mcp_sync
from .mcps import mcp_uninstall as mcp_uninstall
from .mcps import render_launch_for_mode as render_launch_for_mode
from .mcps import (
    render_mcp_definition_for_mode as render_mcp_definition_for_mode,
)
from .mcps import resolve_mcp_targets as resolve_mcp_targets
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
from .sync import sync_files as sync_files
from .system import system_show as system_show
from .system import system_sync as system_sync
from .types import CONFIG_HEADER as CONFIG_HEADER
from .types import McpTarget as McpTarget
from .types import SyncResult as SyncResult
from .types import ToolConfig as ToolConfig
from .types import WorkspaceContext as WorkspaceContext
from .types import get_context as get_context
from .types import init_paths as init_paths
from .types import set_context as set_context
