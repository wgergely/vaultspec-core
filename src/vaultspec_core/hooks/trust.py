"""Operator consent records for the shell commands declared by workspace hooks.

A hook file is authored content under ``.vaultspec/hooks/``. The sharing policy
keeps that directory in git, so a hook definition travels with a clone the same
way a rule or a skill does - and unlike a rule or a skill, a hook declares a
shell command that the CLI will spawn with the operator's own environment. The
file alone therefore cannot be the authority for whether that command may run.

This module holds the second authority: a consent ledger stored under the
machine-global VaultSpec home (:func:`~vaultspec_core.core.home.core_home_layout`)
rather than inside the workspace, so that no checkout, archive, or clone can
carry its own approval. Consent is recorded per hook FILE and pinned to that
file's content digest, so editing a trusted hook - or a pull that rewrites one -
withdraws the approval until an operator grants it again.

Every failure mode answers "not trusted": a missing ledger, an unreadable or
malformed ledger, an unknown schema version, an unreadable hook file, a digest
mismatch, and a hook object with no backing file all deny execution. There is no
input to this module that can turn an error into an approval.

Key exports: :func:`trust_file_path`, :func:`hook_digest`, :func:`is_trusted`,
:func:`partition_by_trust`, :func:`grant`, :func:`revoke`. Enforced by
:func:`vaultspec_core.hooks.engine.trigger`.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
from typing import TYPE_CHECKING, cast

from ..core.home import core_home_layout

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from .engine import Hook

logger = logging.getLogger(__name__)

__all__ = [
    "TRUST_FILE_NAME",
    "TRUST_SCHEMA_VERSION",
    "grant",
    "granted_digests",
    "hook_digest",
    "is_trusted",
    "partition_by_trust",
    "revoke",
    "scope_key",
    "trust_file_path",
]

#: Ledger filename below the machine-global VaultSpec home.
TRUST_FILE_NAME = "hook-trust.json"

#: Ledger schema version. An unrecognised version denies every hook rather than
#: guessing at a payload a future release wrote.
TRUST_SCHEMA_VERSION = 1

_SCOPES_KEY = "scopes"
_HOOKS_KEY = "hooks"
_GRANTED_AT_KEY = "granted_at"
_VERSION_KEY = "version"


def trust_file_path(home: Path | None = None) -> Path:
    """Resolve the consent ledger's path below the machine-global home.

    ``home`` names the VaultSpec home itself, exactly as
    :func:`~vaultspec_core.core.home.core_home_layout` takes it. The explicit
    form exists for real-filesystem tests that must not read or write the
    operator's own ledger; production callers pass nothing.
    """
    return core_home_layout(home).root / TRUST_FILE_NAME


def scope_key(hooks_dir: Path) -> str:
    """Return the ledger key identifying one workspace's hooks directory.

    The key is the fully resolved, case-normalised path of the directory the
    hook files were loaded from. Resolving it means a symlinked or relative
    route to the same directory reuses one grant; normalising the case means a
    Windows path that differs only in casing cannot open a second, unapproved
    scope. Because the key is an absolute local path, a ledger copied to another
    machine or another checkout location grants nothing there.
    """
    try:
        resolved = hooks_dir.resolve()
    except OSError:
        resolved = hooks_dir.absolute()
    return os.path.normcase(str(resolved))


def hook_digest(path: Path) -> str | None:
    """Return the ``sha256:`` digest of a hook file, or ``None`` if unreadable.

    The digest covers the raw bytes, so any edit to a trusted hook - including
    one that only changes whitespace inside the command - produces a different
    digest and withdraws consent.
    """
    try:
        payload = path.read_bytes()
    except OSError:
        logger.warning("Cannot digest hook file %s; treating as untrusted", path)
        return None
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _read_ledger(home: Path | None) -> dict[str, dict[str, str]]:
    """Read the ledger into ``{scope: {filename: digest}}``, or empty on doubt.

    Every unreadable, malformed, or unrecognised-version ledger reads as empty,
    which denies every hook. Corruption must never widen consent.
    """
    path = trust_file_path(home)
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.warning("Unreadable hook consent ledger %s; no hook is trusted", path)
        return {}

    if not isinstance(raw, dict):
        return {}
    document = cast("dict[str, object]", raw)
    if document.get(_VERSION_KEY) != TRUST_SCHEMA_VERSION:
        logger.warning(
            "Hook consent ledger %s has unsupported version %r; no hook is trusted",
            path,
            document.get(_VERSION_KEY),
        )
        return {}

    scopes_raw = document.get(_SCOPES_KEY)
    if not isinstance(scopes_raw, dict):
        return {}

    ledger: dict[str, dict[str, str]] = {}
    for scope, entry in cast("dict[str, object]", scopes_raw).items():
        if not isinstance(entry, dict):
            continue
        hooks_raw = cast("dict[str, object]", entry).get(_HOOKS_KEY)
        if not isinstance(hooks_raw, dict):
            continue
        grants = {
            name: value
            for name, value in cast("dict[str, object]", hooks_raw).items()
            if isinstance(value, str)
        }
        if grants:
            ledger[scope] = grants
    return ledger


def _write_ledger(ledger: dict[str, dict[str, str]], home: Path | None) -> Path:
    """Persist the ledger, creating the machine-global home if needed."""
    from ..core.helpers import atomic_write

    now = datetime.datetime.now(tz=datetime.UTC).isoformat()
    document = {
        _VERSION_KEY: TRUST_SCHEMA_VERSION,
        _SCOPES_KEY: {
            scope: {_HOOKS_KEY: dict(sorted(grants.items())), _GRANTED_AT_KEY: now}
            for scope, grants in sorted(ledger.items())
        },
    }
    path = trust_file_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return path


def granted_digests(hooks_dir: Path, home: Path | None = None) -> dict[str, str]:
    """Return the recorded ``{filename: digest}`` grants for one hooks directory."""
    return _read_ledger(home).get(scope_key(hooks_dir), {})


def is_trusted(source_path: Path | None, home: Path | None = None) -> bool:
    """Report whether a hook file's current content carries operator consent.

    A hook with no backing file (``source_path`` is ``None``) is never trusted:
    the ledger can only vouch for bytes it has seen, so a synthesised hook has
    nothing to match against.
    """
    if source_path is None:
        return False
    grants = granted_digests(source_path.parent, home)
    recorded = grants.get(source_path.name)
    if recorded is None:
        return False
    return recorded == hook_digest(source_path)


def partition_by_trust(
    hooks: Iterable[Hook], home: Path | None = None
) -> tuple[list[Hook], list[Hook]]:
    """Split hooks into ``(trusted, untrusted)`` by consent-ledger lookup.

    The caller decides what to do with each half: :func:`.engine.trigger`
    executes only the first, while the CLI consent gate uses the second to
    describe exactly what it is asking the operator to approve.
    """
    trusted: list[Hook] = []
    untrusted: list[Hook] = []
    for hook in hooks:
        (trusted if is_trusted(hook.source_path, home) else untrusted).append(hook)
    return trusted, untrusted


def grant(paths: Iterable[Path], home: Path | None = None) -> list[Path]:
    """Record consent for each hook file at its current content.

    Files that cannot be digested are skipped rather than recorded blind.

    Returns:
        The paths actually written into the ledger, in the order supplied.
    """
    ledger = _read_ledger(home)
    recorded: list[Path] = []
    for path in paths:
        digest = hook_digest(path)
        if digest is None:
            continue
        ledger.setdefault(scope_key(path.parent), {})[path.name] = digest
        recorded.append(path)
    if recorded:
        _write_ledger(ledger, home)
    return recorded


def revoke(hooks_dir: Path, home: Path | None = None) -> int:
    """Drop every grant recorded for one hooks directory.

    Returns:
        The number of hook files whose consent was withdrawn.
    """
    ledger = _read_ledger(home)
    dropped = ledger.pop(scope_key(hooks_dir), {})
    if dropped:
        _write_ledger(ledger, home)
    return len(dropped)
