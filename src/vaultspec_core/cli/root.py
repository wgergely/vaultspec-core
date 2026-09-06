"""Root Typer application: global callback, options, and top-level commands.

Mounts :mod:`.vault_cmd` and :mod:`.spec_cmd` sub-groups and defines
``install``, ``uninstall``, and ``sync`` commands that delegate to
:mod:`vaultspec_core.core.commands`. Exposes :func:`run` as the console-script
entry point. Depends on :mod:`vaultspec_core.config.workspace` for workspace
resolution and :mod:`vaultspec_core.core.types` for global path initialization.

This module is the public surface for the root command group: the Typer app
instance and every command implementation live in sibling modules, split
along seam (:mod:`.root_app` for the app instance and global callback,
:mod:`.root_preflight` for the shared pre-flight helper, :mod:`.root_install`
for ``install``/``uninstall``, :mod:`.root_sync` for ``sync``, and
:mod:`.root_doctor` for ``doctor``/``check-providers``). Importing this
module registers every command onto :data:`app` and re-exports the full
prior public surface so no import site outside this package needs to change.
"""

from __future__ import annotations

# Each sibling module defines its own Typer app instance (or, for a single
# top-level command, a plain function); mounting them onto ``app`` happens
# explicitly below, in the original definition order, rather than relying on
# import order (which isort/ruff would otherwise alphabetize and so silently
# reorder the generated CLI reference and the ``--help`` command listing).
# The names pulled in here are re-exported for compatibility with call sites
# that imported them directly from this module.
from vaultspec_core.cli.root_app import app, main
from vaultspec_core.cli.root_doctor import cmd_check_providers, cmd_doctor
from vaultspec_core.cli.root_install import cmd_install, cmd_uninstall
from vaultspec_core.cli.root_preflight import logger, run_preflight
from vaultspec_core.cli.root_sync import (
    cmd_sync,
    collect_sync_outcomes,
    infer_label,
    reject_core_sync_target,
    render_sync_dry_run,
    render_sync_post_notices,
    resolve_active_sync_names,
    single_item_result,
)

app.command("install")(cmd_install)
app.command("uninstall")(cmd_uninstall)
app.command("sync")(cmd_sync)
app.command("check-providers", hidden=True)(cmd_check_providers)
app.command("doctor")(cmd_doctor)


def _register_subcommands() -> None:
    """Mount sub-apps with deferred imports to avoid circular dependencies."""
    from .config_cmd import config_app
    from .migrations_cmd import migrations_app
    from .spec_cmd import spec_app
    from .status_cmd import register as register_status
    from .vault_cmd import vault_app

    # The zeroth-move orientation verb is top-level, not nested
    # under `vault`; it is the most reachable command for an unknown project.
    register_status(app)

    app.add_typer(vault_app, name="vault")
    app.add_typer(spec_app, name="spec")
    app.add_typer(migrations_app, name="migrations")
    app.add_typer(config_app, name="config")


_register_subcommands()


# ---- Entry point -------------------------------------------------------------


def run() -> None:
    """CLI entry point for console scripts."""
    from vaultspec_core.cli._errors import run_app

    run_app(app)


if __name__ == "__main__":
    run()


__all__ = [
    "app",
    "cmd_check_providers",
    "cmd_doctor",
    "cmd_install",
    "cmd_sync",
    "cmd_uninstall",
    "collect_sync_outcomes",
    "infer_label",
    "logger",
    "main",
    "reject_core_sync_target",
    "render_sync_dry_run",
    "render_sync_post_notices",
    "resolve_active_sync_names",
    "run",
    "run_preflight",
    "single_item_result",
]
