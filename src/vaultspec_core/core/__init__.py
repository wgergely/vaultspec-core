"""Expose the core resource-management and sync surface for vaultspec.

The `core` package contains the synchronized framework resources and the
helpers used to materialize them into a workspace. Its submodules cover
`agents`, `rules`, `skills`, and `system` resources, plus `config_gen`,
`resources`, `sync`, `types`, and helper utilities that support bootstrap and
distribution.
"""

from .agents import agents_add as agents_add
from .agents import agents_list as agents_list
from .agents import agents_sync as agents_sync
from .agents import collect_agents as collect_agents
from .agents import transform_agent as transform_agent
from .config_gen import config_show as config_show
from .config_gen import config_sync as config_sync
from .helpers import atomic_write as atomic_write
from .helpers import build_file as build_file
from .helpers import ensure_dir as ensure_dir
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
from .sync import print_summary as print_summary
from .sync import sync_files as sync_files
from .system import system_show as system_show
from .system import system_sync as system_sync
from .types import AGENTS_SRC_DIR as AGENTS_SRC_DIR
from .types import CONFIG_HEADER as CONFIG_HEADER
from .types import HOOKS_DIR as HOOKS_DIR
from .types import ROOT_DIR as ROOT_DIR
from .types import RULES_SRC_DIR as RULES_SRC_DIR
from .types import SKILLS_SRC_DIR as SKILLS_SRC_DIR
from .types import SYSTEM_SRC_DIR as SYSTEM_SRC_DIR
from .types import TARGET_DIR as TARGET_DIR
from .types import TEMPLATES_DIR as TEMPLATES_DIR
from .types import TOOL_CONFIGS as TOOL_CONFIGS
from .types import SyncResult as SyncResult
from .types import ToolConfig as ToolConfig
from .types import init_paths as init_paths
