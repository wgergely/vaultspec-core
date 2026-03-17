"""CLI package -- the user-facing command surface for vaultspec-core.

Organized into domain groups:
- root: install, uninstall, sync (top-level commands + global options)
- vault_cmd: vault stats, vault list, vault add, vault feature, vault check
- spec_cmd: spec rules, spec skills, spec agents, spec system, spec hooks
"""

from .root import app, run

__all__ = ["app", "run"]
