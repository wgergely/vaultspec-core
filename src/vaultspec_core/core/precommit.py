"""Render and reconcile vaultspec-core's managed pre-commit hooks.

Covers the mode-parameterized canonical hook definitions (entry prefix, hook
metadata, and the derived canonical hook list/entry map) plus the
``.pre-commit-config.yaml`` scaffolding and stripping logic that keeps a
project's hook file in sync with them.
"""

from __future__ import annotations

import io
import logging
from contextlib import nullcontext
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML, YAMLError

from .enums import InstallMode, PrecommitHook, render_mode
from .helpers import advisory_lock, atomic_write
from .prek_boundary import PrekBoundaryState, collect_prek_boundary
from .workspace_mode import (
    CORE_DISTRIBUTION_NAME,
    read_hooks_declaration,
    resolve_render_mode,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ALL_MANAGED_HOOK_IDS",
    "CANONICAL_ENTRY_PREFIX",
    "CANONICAL_HOOK_ENTRIES",
    "CANONICAL_HOOK_IDS",
    "CANONICAL_PRECOMMIT_HOOKS",
    "canonical_hook_entries_for_mode",
    "canonical_precommit_hooks_for_mode",
    "entry_prefix_for_mode",
    "hook_defs_for_mode",
    "scaffold_precommit",
    "strip_managed_precommit_hooks",
]


def _as_mapping(value: object) -> dict[str, Any] | None:
    """Narrow *value* to a plain dict, or ``None`` when it isn't one.

    A thin wrapper around ``isinstance(value, dict)``: narrowing an
    honestly-``Any`` YAML payload via a bare ``isinstance(x, dict)`` only
    recovers ``dict[Unknown, Unknown]``, so every downstream ``.get()`` stays
    partially unknown until the result is re-typed here.
    """
    if isinstance(value, dict):
        return cast("dict[str, Any]", value)
    return None


def _as_list(value: object) -> list[Any] | None:
    """Narrow *value* to a plain list, or ``None`` when it isn't one.

    See :func:`_as_mapping` - the same bare-``isinstance`` narrowing gap
    applies to lists pulled out of a YAML payload.
    """
    if isinstance(value, list):
        return cast("list[Any]", value)
    return None


# The canonical CLI-invocation prefix each pre-commit hook entry is built from,
# keyed by provisioning mode. Dependency mode resolves ``vaultspec-core`` through
# the target project's own venv via ``uv run`` (byte-identical to the single
# prefix that existed before mode-awareness); tool mode resolves it through an
# ephemeral ``uvx`` invocation so it never enters the project's dependency set.
_MODE_ENTRY_PREFIX: dict[InstallMode, str] = {
    InstallMode.DEPENDENCY: "uv run --no-sync vaultspec-core",
    InstallMode.TOOL: "uvx --from vaultspec-core vaultspec-core",
}


def entry_prefix_for_mode(mode: InstallMode) -> str:
    """Return the canonical hook-entry command prefix for *mode*.

    The lookup is keyed by the *rendered* mode (via
    :func:`~vaultspec_core.core.enums.render_mode`), so
    :attr:`~vaultspec_core.core.enums.InstallMode.DEV` resolves to the same
    ``uv run`` prefix as :attr:`~vaultspec_core.core.enums.InstallMode.DEPENDENCY`
    rather than needing its own table entry. This keeps the prefix table a
    two-shape render surface even as the mode vocabulary carries the third
    dev-scoped bookkeeping member.
    """
    return _MODE_ENTRY_PREFIX[render_mode(mode)]


#: Backward-compatible module-level prefix, pinned to dependency mode. Modules
#: and diagnostics that still assume a single prefix (the doctor's
#: canonical-entry check) read this until they are made mode-aware; the
#: mode-parameterized renderers derive their prefix from
#: :func:`entry_prefix_for_mode` instead.
CANONICAL_ENTRY_PREFIX = entry_prefix_for_mode(InstallMode.DEPENDENCY)


# Mode-independent pre-commit hook metadata: the CLI subcommand each hook
# invokes plus its non-entry pre-commit fields. The ``entry`` is derived per
# mode by prefixing the subcommand with the mode's canonical entry prefix. The
# insertion order here is the order hooks are scaffolded into
# ``.pre-commit-config.yaml`` and must be preserved.
_HOOK_SUBCOMMAND: dict[PrecommitHook, str] = {
    # A pure gate, deliberately not ``--fix``. Unattended corpus-mutating
    # repair from inside a commit is retired by the modified-stamp-provenance
    # decision: ``pass_filenames: false`` hands the hook the whole corpus as
    # blast radius no matter what the commit touches, a hook-time fix writes
    # changes nobody reviewed into commits that are not about them, and the
    # hook runner's revert-based staging protocol makes hook-time tree
    # mutation unsafe in shared worktrees. The non-fix run is an exact,
    # deterministic preview, so a failing gate names precisely what a
    # deliberate operator-run ``--fix`` will do. The hook id keeps its
    # historical ``vault-fix`` spelling so existing installs are updated in
    # place rather than accumulating a second, near-duplicate entry.
    PrecommitHook.VAULT_FIX: "vault check all",
    PrecommitHook.VAULT_SANITIZE_ANNOTATIONS: "vault sanitize annotations",
    PrecommitHook.CHECK_PROVIDER_ARTIFACTS: "check-providers",
    # ``--gate-errors`` folds the doctor's warning exit (1) to 0 so the gate
    # blocks only on errors. Warning-level provider-mirror lag is the expected
    # steady state after any builtins change - check-provider-artifacts forbids
    # committing the regenerated mirror - so a warning-strict gate would
    # deadlock every commit. This is the canonical entry, not a hand-hardened
    # local override, so sync renders it directly rather than clobbering it.
    PrecommitHook.SPEC_CHECK: "spec doctor --gate-errors",
}
_HOOK_META: dict[PrecommitHook, dict[str, object]] = {
    PrecommitHook.VAULT_FIX: {"name": "Vault gate", "types": ["markdown"]},
    PrecommitHook.VAULT_SANITIZE_ANNOTATIONS: {
        "name": "Vault sanitize annotations",
        "types": ["markdown"],
    },
    PrecommitHook.CHECK_PROVIDER_ARTIFACTS: {
        "name": "Check provider artifacts",
        "always_run": True,
    },
    PrecommitHook.SPEC_CHECK: {"name": "Spec check", "types": ["markdown"]},
}


def hook_defs_for_mode(mode: InstallMode) -> dict[PrecommitHook, dict[str, object]]:
    """Return the hook-field map for *mode*, keyed by :class:`PrecommitHook`.

    Each value merges the mode-independent metadata (name, filter fields) with
    an ``entry`` built from the mode's canonical prefix and the hook's
    subcommand, so dependency mode renders ``uv run --no-sync vaultspec-core
    ...`` and tool mode renders ``uvx --from vaultspec-core vaultspec-core
    ...``.
    """
    prefix = entry_prefix_for_mode(mode)
    defs: dict[PrecommitHook, dict[str, object]] = {}
    for hook, meta in _HOOK_META.items():
        # Preserve the original field order (name, entry, then the hook's
        # filter field) so the scaffolded YAML is byte-stable across modes.
        value: dict[str, object] = {"name": meta["name"]}
        value["entry"] = f"{prefix} {_HOOK_SUBCOMMAND[hook]}"
        for key, field in meta.items():
            if key != "name":
                value[key] = field
        defs[hook] = value
    return defs


def canonical_precommit_hooks_for_mode(mode: InstallMode) -> list[dict[str, object]]:
    """Return the full canonical pre-commit hook list rendered for *mode*."""
    return [
        {
            "id": hook.value,
            **meta,
            "language": "system",
            "pass_filenames": False,
        }
        for hook, meta in hook_defs_for_mode(mode).items()
    ]


def canonical_hook_entries_for_mode(mode: InstallMode) -> dict[str, str]:
    """Return each canonical hook ID mapped to its expected entry for *mode*."""
    return {
        hook.value: str(meta["entry"])
        for hook, meta in hook_defs_for_mode(mode).items()
    }


CANONICAL_HOOK_IDS: frozenset[str] = frozenset(h.value for h in PrecommitHook)

#: Backward-compatible module-level canonical hooks and entries, pinned to
#: dependency mode. The doctor's canonical-entry check still imports
#: ``CANONICAL_HOOK_ENTRIES`` and compares against the single dependency-mode
#: shape; making that check mode-aware is the next phase. ``scaffold_precommit``
#: renders through :func:`canonical_precommit_hooks_for_mode` instead.
CANONICAL_PRECOMMIT_HOOKS: list[dict[str, object]] = canonical_precommit_hooks_for_mode(
    InstallMode.DEPENDENCY
)
CANONICAL_HOOK_ENTRIES: dict[str, str] = canonical_hook_entries_for_mode(
    InstallMode.DEPENDENCY
)

# All managed hook IDs for uninstall filtering.
ALL_MANAGED_HOOK_IDS: frozenset[str] = CANONICAL_HOOK_IDS


def _precommit_yaml() -> YAML:
    """Return a round-trip YAML handler for ``.pre-commit-config.yaml``.

    Round-trip mode preserves the parts of an author-maintained config that a
    plain ``safe_load`` + ``dump`` cycle would silently rewrite: explanatory
    comments, the single-quoted literal form of ``exclude``/``files`` regexes,
    and long ``entry`` scalars that a re-emitter would otherwise line-wrap.
    Preserving them is what makes a full ``sync`` over a correctly-rendered
    config a byte-for-byte no-op instead of a spurious diff.

    The sequence indent is pinned to the non-indented block style
    (``sequence=2, offset=0``) so a freshly scaffolded config matches the
    historical layout, and ``width`` is raised so entry scalars are never
    folded onto continuation lines.
    """
    handler = YAML()
    handler.preserve_quotes = True
    handler.width = 4096
    handler.indent(mapping=2, sequence=2, offset=0)
    return handler


def _dump_precommit_yaml(handler: YAML, data: dict[str, Any]) -> str:
    """Serialise *data* to a string through the round-trip *handler*."""
    buffer = io.StringIO()
    handler.dump(data, buffer)
    return buffer.getvalue()


def _drop_managed_hook_entries(repos: list[Any]) -> bool:
    """Delete vaultspec-managed hooks from the ``repos`` sequence in place.

    Mutates the loaded structure so surviving non-vaultspec hooks keep their
    comments and quoting, and drops any local repo left without hooks.

    Returns:
        ``True`` when a managed hook was deleted.
    """
    changed = False
    for r in list(repos):
        record = _as_mapping(r)
        if record is None or record.get("repo") != "local":
            continue
        hooks = _as_list(record.get("hooks", []))
        if hooks is None:
            continue
        managed_idx = [
            i
            for i, h in enumerate(hooks)
            if (hook := _as_mapping(h)) is not None
            and hook.get("id") in ALL_MANAGED_HOOK_IDS
        ]
        for i in reversed(managed_idx):
            del hooks[i]
        if managed_idx:
            changed = True
        if not hooks:
            repos.remove(r)
    return changed


def strip_managed_precommit_hooks(config_file: Path) -> bool:
    """Remove vaultspec-managed hooks from an existing ``.pre-commit-config.yaml``.

    The file is rewritten in place, or deleted when nothing but the managed
    hooks remained.  Read, parse, and write failures are absorbed: uninstall
    residue removal is best-effort and never fails the run.

    Returns:
        ``True`` when the config was rewritten or deleted.
    """
    handler = _precommit_yaml()
    try:
        loaded: object = handler.load(config_file.read_text(encoding="utf-8"))
        data = _as_mapping(loaded)
        if data is None:
            return False
        repos = _as_list(data.get("repos", []))
        if repos is None:
            return False
        if not _drop_managed_hook_entries(repos):
            return False

        if repos:
            atomic_write(config_file, _dump_precommit_yaml(handler, data))
            return True
        del data["repos"]
        if data:
            atomic_write(config_file, _dump_precommit_yaml(handler, data))
        else:
            config_file.unlink()
    # UnicodeDecodeError subclasses ValueError, not OSError, so a file that
    # exists and cannot be decoded escaped this net and surfaced as a raw
    # traceback (issue #407).
    except (YAMLError, OSError, UnicodeDecodeError):
        return False
    return True


def _log_prek_boundary_status(target: Path, boundary: PrekBoundaryState) -> None:
    """Log why ``.pre-commit-config.yaml`` scaffolding is being skipped.

    Distinguishes a healthy transplant (the canonical hooks already live in
    ``prek.toml``) from stranded hooks that ``spec precommit migrate`` still
    needs to move, and flags a co-present, now-superseded YAML config in
    either case.
    """
    config_file = target / ".pre-commit-config.yaml"
    if boundary.hooks_present:
        logger.info(
            "prek.toml at %s already carries the vaultspec-core hooks; "
            "skipping .pre-commit-config.yaml scaffold.",
            target,
        )
        if config_file.exists():
            logger.info(
                "A superseded .pre-commit-config.yaml is still present at %s. "
                "prek reads prek.toml exclusively; remove the YAML config "
                "once nothing else consumes it.",
                target,
            )
        return
    logger.info(
        "prek.toml detected at %s; skipping .pre-commit-config.yaml "
        "scaffold. Run 'vaultspec-core spec precommit migrate' to "
        "transplant the vaultspec-core hooks into prek.toml.",
        target,
    )
    if config_file.exists():
        logger.warning(
            "Both prek.toml and .pre-commit-config.yaml are present at "
            "%s and prek.toml lacks the vaultspec-core hooks. prek "
            "reads prek.toml exclusively; vaultspec will not refresh "
            "the YAML hooks. Run 'vaultspec-core spec precommit "
            "migrate' to transplant them.",
            target,
        )


def _load_existing_precommit_config(
    config_file: Path, handler: YAML
) -> dict[str, Any] | None:
    """Load and validate an existing ``.pre-commit-config.yaml``.

    Returns:
        The parsed mapping, with its ``repos`` key defaulted to a list, or
        ``None`` when the file cannot be read/parsed, isn't a mapping, or its
        ``repos`` key isn't list-shaped - any of which tells the caller to
        skip scaffolding for this run rather than risk corrupting a config
        it doesn't recognize.
    """
    try:
        raw = config_file.read_text(encoding="utf-8")
        loaded: object = handler.load(raw) or {}
    # UnicodeDecodeError subclasses ValueError, not OSError, so a file that
    # exists and cannot be decoded escaped this net and surfaced as a raw
    # traceback (issue #407).
    except (YAMLError, OSError, UnicodeDecodeError):
        return None
    data = _as_mapping(loaded)
    if data is None:
        return None
    if _as_list(data.setdefault("repos", [])) is None:
        return None
    return data


def _merge_local_repo_hooks(
    existing_hooks: list[Any], canonical_hooks: list[dict[str, object]]
) -> bool:
    """Reconcile *existing_hooks* against *canonical_hooks* in place.

    Missing hooks are appended; hooks whose entry drifted from the canonical
    pattern are updated in place; hooks already canonical are left untouched.

    Returns:
        ``True`` when *existing_hooks* was changed.
    """
    existing_by_id: dict[Any, dict[str, Any]] = {}
    for raw_hook in existing_hooks:
        hook = _as_mapping(raw_hook)
        if hook is not None:
            existing_by_id[hook.get("id")] = hook
    changed = False
    for canonical in canonical_hooks:
        hook_id = str(canonical["id"])
        existing = existing_by_id.get(hook_id)
        if existing is None:
            existing_hooks.append(dict(canonical))
            logger.info("Added pre-commit hook '%s'", hook_id)
            changed = True
            continue
        if existing.get("entry") == canonical["entry"]:
            continue
        existing["entry"] = canonical["entry"]
        logger.info("Updated pre-commit hook '%s' entry to canonical pattern", hook_id)
        changed = True
    return changed


def _reconcile_precommit_repos(
    data: dict[str, Any], canonical_hooks: list[dict[str, object]]
) -> bool:
    """Reconcile the local repo's hooks in *data* against *canonical_hooks*.

    Creates the local repo when none exists; otherwise merges via
    :func:`_merge_local_repo_hooks`.

    Returns:
        ``True`` when *data* should be written back to disk.
    """
    repos = cast("list[Any]", data["repos"])
    local_repos = [
        rec
        for r in repos
        if (rec := _as_mapping(r)) is not None and rec.get("repo") == "local"
    ]
    if not local_repos:
        repos.append({"repo": "local", "hooks": [dict(h) for h in canonical_hooks]})
        return True

    local_repo = local_repos[0]
    existing_hooks = _as_list(local_repo.setdefault("hooks", []))
    if existing_hooks is None:
        return False
    return _merge_local_repo_hooks(existing_hooks, canonical_hooks)


def scaffold_precommit(
    target: Path, *, dry_run: bool = False, mode: InstallMode | None = None
) -> list[tuple[str, str]]:
    """Scaffold or merge vaultspec-core hooks into .pre-commit-config.yaml.

    Ensures the full canonical hook set is present with canonical entry
    patterns.  Existing hooks with matching IDs are updated to the
    canonical entry; missing hooks are appended.

    The entry each hook is rendered with follows the resolved provisioning
    mode: dependency mode keeps the ``uv run --no-sync vaultspec-core`` prefix,
    tool mode uses ``uvx --from vaultspec-core vaultspec-core``. When *mode* is
    ``None`` it is resolved from the committed workspace declaration via
    :func:`~vaultspec_core.core.workspace_mode.resolve_render_mode`, whose
    legacy-absent rule renders dependency mode so a workspace provisioned
    before ``install-mode`` keeps its existing hook entries. The fresh-install
    caller passes its resolved mode explicitly, because the declaration is
    written only after scaffolding.

    Skips scaffolding entirely in two cases.

    The first is a committed opt-out: a workspace whose declaration sets
    ``hooks.pre_commit`` to ``false`` has decided it runs its gates explicitly
    and forbids a commit hook, so no install or sync writes the file. The
    declaration is read on every call rather than resolved once at provision
    time, so the choice survives every later run instead of being re-decided by
    whichever verb happens to reach here.

    The second is ``prek.toml`` being present at *target* (assessed through
    :func:`~vaultspec_core.core.prek_boundary.collect_prek_boundary`):
    prek reads ``prek.toml`` exclusively and silently ignores a co-present
    ``.pre-commit-config.yaml``, so writing the YAML would leave hooks prek
    never runs. The operator transplants hooks into ``prek.toml`` with
    ``spec precommit migrate``; the log messages distinguish a healthy
    transplant (hooks already in ``prek.toml``) from stranded hooks.

    Neither skip deletes an existing ``.pre-commit-config.yaml``. Declining
    future scaffolding is a policy statement; removing a file the operator may
    still have reasons to keep is a destructive act they ask for explicitly.
    """
    if not read_hooks_declaration(target).pre_commit:
        logger.info(
            "The workspace declaration at %s sets hooks.pre_commit to false; "
            "skipping .pre-commit-config.yaml scaffolding.",
            target,
        )
        return []

    if mode is None:
        mode = resolve_render_mode(target, package=CORE_DISTRIBUTION_NAME)
    canonical_hooks = canonical_precommit_hooks_for_mode(mode)

    boundary = collect_prek_boundary(target, mode=mode)
    if boundary.owns_boundary:
        _log_prek_boundary_status(target, boundary)
        return []

    config_file = target / ".pre-commit-config.yaml"
    handler = _precommit_yaml()
    result = [(".pre-commit-config.yaml", "precommit")]

    with nullcontext() if dry_run else advisory_lock(config_file):
        if not config_file.exists():
            if not dry_run:
                data = {
                    "repos": [
                        {"repo": "local", "hooks": [dict(h) for h in canonical_hooks]}
                    ]
                }
                atomic_write(config_file, _dump_precommit_yaml(handler, data))
            return result

        data = _load_existing_precommit_config(config_file, handler)
        if data is None:
            return []
        if not _reconcile_precommit_repos(data, canonical_hooks):
            return []

        if not dry_run:
            atomic_write(config_file, _dump_precommit_yaml(handler, data))
        return result
