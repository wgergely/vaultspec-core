"""User-facing CLI surface for vaultspec-core, built on Typer.

Exports :func:`app` (the root :class:`typer.Typer` instance) and :func:`run`
(the ``__main__`` entry point). Subgroups: ``root`` (install/uninstall/sync),
``vault_cmd`` (vault stats/list/add/feature/check), and ``spec_cmd``
(spec rules/skills/agents/system/hooks). Depends on :mod:`vaultspec_core.config`
and :mod:`vaultspec_core.hooks`.
"""

from .root import app, run

__all__ = ["app", "run"]
