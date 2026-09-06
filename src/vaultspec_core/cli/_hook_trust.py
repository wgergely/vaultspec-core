"""The operator-facing consent gate for workspace hooks.

:func:`vaultspec_core.hooks.engine.trigger` already refuses to spawn a command
that :mod:`vaultspec_core.hooks.trust` has not matched against a consent record,
so nothing here is what makes the product safe. What this module adds is the
only thing a refusal is missing: a way for the operator to say yes, and an
explanation of what they are saying yes to.

The gate is deliberately a CLI concern rather than an engine one. Asking is an
interactive act at a terminal, and the engine runs in contexts - CI, the MCP
server, ``--json`` pipelines - that have no operator behind them. Keeping the
question here means the enforcement path has no branch that could ever answer it
automatically: when this module cannot reach a human it explains the refusal and
returns, and the hooks simply do not run.

Key exports: :func:`consent_gate`, :func:`describe_hook`,
:func:`operator_present`.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from pathlib import Path

    from vaultspec_core.hooks import Hook

__all__ = ["consent_gate", "describe_hook", "operator_present"]

#: Environment variables whose mere presence means no operator is watching.
#: ``CI`` is the near-universal convention; the VaultSpec-specific name lets an
#: operator assert the same thing for a wrapper script that CI does not set.
_NON_INTERACTIVE_ENV = ("CI", "VAULTSPEC_NON_INTERACTIVE")

#: Why a hook needs approval, in the terms that make the decision answerable:
#: what runs, as whom, and why the repository itself cannot vouch for it. A
#: prompt the operator does not understand is a prompt they click through.
_RATIONALE = (
    "Each of these hook files ships with this repository and declares a shell "
    "command that would run now, on this machine, as you - with your "
    "environment, your credentials, and this workspace as its working "
    "directory. A repository cannot approve its own hooks, so approval is "
    "recorded outside it and is tied to each file's current contents; editing "
    "a hook, or pulling a change to one, asks again."
)


def describe_hook(hook: Hook, target_dir: Path | None = None) -> list[str]:
    """Render one untrusted hook as the lines an operator needs to judge it.

    The commands are shown verbatim and unwrapped. An approval prompt that
    summarises or truncates the command is worse than no prompt, because it
    invites a yes to something other than what will run.
    """
    location = hook.source_path
    label = str(location) if location is not None else "<no file>"
    if location is not None and target_dir is not None:
        try:
            label = str(location.relative_to(target_dir))
        except ValueError:
            label = str(location)
    lines = [f"  {hook.name}  ({label})"]
    lines.extend(
        f"    {action.action_type}: {action.command}" for action in hook.actions
    )
    return lines


def consent_gate(
    event: str,
    *,
    json_output: bool = False,
    home: Path | None = None,
) -> list[str]:
    """Offer the operator the choice to trust the hooks an event would run.

    Loads the workspace's hooks for ``event``, and for any that carry no
    consent record either asks for one (at an interactive terminal) or explains
    why they will be skipped (anywhere else). Granting writes the consent
    record; declining, redirected input, and ``--json`` all leave it unwritten.

    Args:
        event: The lifecycle event whose hooks are about to be considered.
        json_output: Whether the calling command is emitting a JSON envelope.
            A machine-readable run has no operator to ask and must not have its
            stdout disturbed, so it never prompts.
        home: Machine-global VaultSpec home holding the consent ledger; tests
            pass their own so they never touch the operator's.

    Returns:
        The names of the hooks that remain untrusted, and will therefore be
        skipped. Empty when every hook for ``event`` may run.
    """
    from vaultspec_core.core.types import get_context
    from vaultspec_core.hooks import grant, load_hooks, partition_by_trust

    try:
        ctx = get_context()
    except LookupError:
        return []

    candidates = [
        hook
        for hook in load_hooks(ctx.hooks_dir)
        if hook.event == event and hook.enabled
    ]
    _, untrusted = partition_by_trust(candidates, home)
    if not untrusted:
        return []

    names = [hook.name for hook in untrusted]
    detail: list[str] = []
    for hook in untrusted:
        detail.extend(describe_hook(hook, ctx.target_dir))

    if json_output or not operator_present():
        _explain_refusal(names, detail)
        return names

    typer.echo("")
    typer.echo(f"Untrusted workspace hooks for '{event}':")
    for line in detail:
        typer.echo(line)
    typer.echo("")
    typer.echo(_RATIONALE)
    typer.echo("")
    try:
        approved = typer.confirm(
            "Run these hooks, and remember this approval?", default=False
        )
    except (typer.Abort, EOFError, KeyboardInterrupt):
        # An interrupt or an exhausted stream is not an answer. It reaches here
        # when a stream that claimed to be a terminal turns out not to carry
        # one, which some Windows shells arrange for a redirected run - the
        # exact case that must never be read as consent. Treat it as a refusal
        # and let the caller continue without the hooks, rather than letting an
        # Abort tear down a sync that is otherwise legitimate.
        approved = False
    if not approved:
        typer.echo("", err=True)
        _explain_refusal(names, [])
        return names

    grant([h.source_path for h in untrusted if h.source_path is not None], home)
    return []


def operator_present() -> bool:
    """Report whether there is a human at a terminal who could answer.

    Three independent signals must all agree before this module will ask a
    question: an interactive stdin to read the answer from, an interactive
    stdout to show the hook commands on, and no environment marker declaring an
    unattended run. Any one of them dissenting means the answer is no, because
    a prompt nobody sees is a prompt nobody consented to.
    """
    if any(name in os.environ for name in _NON_INTERACTIVE_ENV):
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _explain_refusal(names: list[str], detail: list[str]) -> None:
    """State on stderr why hooks were skipped, and how to approve them.

    Written to stderr so a ``--json`` caller's stdout stays a single envelope,
    and phrased as an instruction to the operator rather than to the process,
    because the operator is the only one who can act on it.
    """
    listed = ", ".join(names)
    typer.echo(
        f"Skipped {len(names)} untrusted workspace hook(s): {listed}",
        err=True,
    )
    for line in detail:
        typer.echo(line, err=True)
    typer.echo(f"  {_RATIONALE}", err=True)
    typer.echo(
        "  Approval cannot be given by a script or a tool call. Review the "
        "files above at a terminal, then run: vaultspec-core spec hooks trust",
        err=True,
    )
