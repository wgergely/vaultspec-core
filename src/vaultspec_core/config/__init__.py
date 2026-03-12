"""Expose configuration and workspace-layout primitives for vaultspec_core.

The `config` package has two responsibilities: `config` defines runtime
settings, environment-variable parsing, and singleton access, while
`workspace` resolves the filesystem layout for `.vault/` and `.vaultspec/`
across standalone, explicit, git, worktree, and container contexts.
"""

from .config import CONFIG_REGISTRY as CONFIG_REGISTRY
from .config import ConfigVariable as ConfigVariable
from .config import VaultSpecConfig as VaultSpecConfig
from .config import get_config as get_config
from .config import parse_csv_list as parse_csv_list
from .config import parse_float_or_none as parse_float_or_none
from .config import parse_int_or_none as parse_int_or_none
from .config import reset_config as reset_config
from .workspace import GitInfo as GitInfo
from .workspace import LayoutMode as LayoutMode
from .workspace import WorkspaceError as WorkspaceError
from .workspace import WorkspaceLayout as WorkspaceLayout
from .workspace import discover_git as discover_git
from .workspace import resolve_workspace as resolve_workspace
