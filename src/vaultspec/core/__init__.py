"""Core configuration and types for vaultspec."""

from .config import VaultSpecConfig, get_config, reset_config
from .workspace import WorkspaceLayout, resolve_workspace

__all__ = [
    "VaultSpecConfig",
    "WorkspaceLayout",
    "get_config",
    "reset_config",
    "resolve_workspace",
]
