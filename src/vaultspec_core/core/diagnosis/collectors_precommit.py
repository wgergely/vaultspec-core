"""Pre-commit hook boundary collectors.

Assesses the state of vaultspec-core hooks, whether they are boundary-owned by
``prek.toml`` or still declared in ``.pre-commit-config.yaml``, and which
install mode a deployed hook entry's canonical shape observes. All imports
from ``core.*`` modules are deferred inside function bodies to prevent import
cycles.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .signals import PrecommitSignal

if TYPE_CHECKING:
    from ..enums import InstallMode

logger = logging.getLogger(__name__)

# ``observed_precommit_mode`` is consumed by :mod:`.collectors_mode` (the
# mode-mismatch collector) and re-exported by :mod:`.collectors`.


def collect_precommit_state(target: Path) -> PrecommitSignal:
    """Assess the state of vaultspec-core hooks in ``.pre-commit-config.yaml``.

    Checks that all canonical hooks are present and use the canonical entry
    pattern (``uv run --no-sync vaultspec-core ...``). When ``prek.toml``
    is present the hook scaffold never runs, so the boundary is assessed
    through
    :func:`~vaultspec_core.core.prek_boundary.collect_prek_boundary` and
    the signal reflects ``prek.toml``'s contents rather than its mere
    existence:

    - canonical hooks present in ``prek.toml`` and no YAML config left
      behind:
      :attr:`~vaultspec_core.core.diagnosis.signals.PrecommitSignal.COMPLETE`;
    - canonical hooks present in ``prek.toml`` with a superseded
      ``.pre-commit-config.yaml`` still on disk:
      :attr:`~vaultspec_core.core.diagnosis.signals.PrecommitSignal.ORPHANED`
      (benign; prek silently ignores the YAML);
    - canonical hooks absent from ``prek.toml`` (including an unparseable
      ``prek.toml``):
      :attr:`~vaultspec_core.core.diagnosis.signals.PrecommitSignal.UNREFRESHABLE`
      - the hooks are genuinely stranded, whatever the YAML says, because
      prek never reads it and sync will not refresh it. The remediation is
      ``spec precommit migrate``.

    Args:
        target: Workspace root directory.

    Returns:
        :class:`~vaultspec_core.core.diagnosis.signals.PrecommitSignal`
        reflecting the observed state.
    """
    from ..prek_boundary import collect_prek_boundary

    boundary = collect_prek_boundary(target)
    if not boundary.owns_boundary:
        return _reassess_against_installation(
            target, _collect_precommit_yaml_state(target)
        )
    if boundary.hooks_present:
        if (target / ".pre-commit-config.yaml").exists():
            return PrecommitSignal.ORPHANED
        return _reassess_against_installation(target, PrecommitSignal.COMPLETE)
    return PrecommitSignal.UNREFRESHABLE


def _hooks_directory(target: Path) -> Path | None:
    """Return the directory git runs hooks from, or ``None`` if unknowable.

    Git is asked rather than assuming ``<target>/.git/hooks``, because that
    assumption is wrong in two ordinary layouts: ``core.hooksPath`` relocates
    the directory outright, and a linked worktree keeps its hooks in the
    common git directory rather than beside its own gitdir.

    Args:
        target: Workspace root directory.

    Returns:
        The resolved hooks directory, or ``None`` when *target* is not a git
        working tree or git is not on ``PATH``.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--git-path", "hooks"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        logger.debug("Cannot resolve the git hooks directory for %s: %s", target, exc)
        return None

    printed = result.stdout.strip()
    if not printed:
        return None
    return (target / printed).resolve()


def precommit_hook_installed(target: Path) -> bool | None:
    """Whether git has a ``pre-commit`` hook installed for *target*.

    Args:
        target: Workspace root directory.

    Returns:
        ``True`` or ``False``, or ``None`` when the question cannot be
        answered - *target* is not a git working tree, or git is unavailable.
        ``None`` is deliberately distinct from ``False``: hooks are not
        stranded merely because this could not look.
    """
    hooks_directory = _hooks_directory(target)
    if hooks_directory is None:
        return None
    return (hooks_directory / "pre-commit").is_file()


def _reassess_against_installation(
    target: Path, signal: PrecommitSignal
) -> PrecommitSignal:
    """Report a complete configuration that nothing will run as such.

    Only :attr:`~vaultspec_core.core.diagnosis.signals.PrecommitSignal.COMPLETE`
    is reassessed. Every other signal already names a fault in the
    configuration itself, and that fault is both more actionable and the thing
    to fix first; an uninstalled hook stacked on a broken config is not a
    second finding worth displacing the first.

    Args:
        target: Workspace root directory.
        signal: The verdict reached from the configuration alone.

    Returns:
        ``NOT_INSTALLED`` when a complete configuration has no installed hook
        to run it, and *signal* unchanged otherwise.
    """
    if signal is not PrecommitSignal.COMPLETE:
        return signal
    if precommit_hook_installed(target) is False:
        return PrecommitSignal.NOT_INSTALLED
    return signal


def _local_precommit_hooks(config_path: Path) -> list[dict[str, object]] | None:
    """Return the hook mappings declared by ``repo: local`` entries.

    Args:
        config_path: Path to ``.pre-commit-config.yaml``.

    Returns:
        The local hook mappings, or ``None`` when the file is absent or cannot
        be parsed. An empty list means the config parsed but declares no local
        hooks, which includes a config whose top level or ``repos`` key carries
        an unexpected shape.
    """
    import yaml

    if not config_path.exists():
        return None

    try:
        data: object = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    # See the note in `core/precommit.py`: an undecodable file is a
    # ValueError, not an OSError (issue #407).
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        logger.warning("Cannot read .pre-commit-config.yaml %s: %s", config_path, exc)
        return None

    if not isinstance(data, dict):
        return []

    repos = cast("dict[str, object]", data).get("repos", [])
    if not isinstance(repos, list):
        return []

    local_hooks: list[dict[str, object]] = []
    for repo in cast("list[object]", repos):
        if isinstance(repo, dict):
            repo_map = cast("dict[str, object]", repo)
            if repo_map.get("repo") == "local":
                hooks = repo_map.get("hooks", [])
                if isinstance(hooks, list):
                    local_hooks.extend(
                        cast("dict[str, object]", h)
                        for h in cast("list[object]", hooks)
                        if isinstance(h, dict)
                    )
    return local_hooks


def _collect_precommit_yaml_state(target: Path) -> PrecommitSignal:
    """Assess ``.pre-commit-config.yaml`` hook state, ignoring ``prek.toml``."""
    from ..commands import CANONICAL_HOOK_IDS, canonical_hook_entries_for_mode
    from ..workspace_mode import resolve_render_mode

    # Derive the expected hook entries from the workspace's resolved mode so a
    # correctly-provisioned tool-mode workspace (uvx entries) is not diagnosed
    # as non-canonical against the dependency-mode shape. resolve_render_mode's
    # legacy-absent rule keeps a pre-install-mode workspace on dependency-shaped
    # expectations. P04 layers a dedicated mode-mismatch signal on top of this.
    expected_entries = canonical_hook_entries_for_mode(resolve_render_mode(target))

    config_path = target / ".pre-commit-config.yaml"
    local_hooks = _local_precommit_hooks(config_path)
    if local_hooks is None:
        # `_local_precommit_hooks` answers None both for an absent file and for
        # one it could not read. Widening its exception net so an undecodable
        # file no longer escapes as a raw traceback means it no longer reaches
        # `_safe_precommit_state`'s handler either, so the distinction has to
        # be made here or the row silently reverts to the benign reading
        # (issue #407).
        if config_path.exists():
            return PrecommitSignal.UNREADABLE
        return PrecommitSignal.NO_FILE

    found_ids = frozenset(
        str(h.get("id")) for h in local_hooks if h.get("id") in CANONICAL_HOOK_IDS
    )

    if not found_ids:
        return PrecommitSignal.NO_HOOKS

    if found_ids != CANONICAL_HOOK_IDS:
        return PrecommitSignal.INCOMPLETE

    # All hooks present - check entry patterns match exactly
    for hook in local_hooks:
        hook_id = hook.get("id")
        if hook_id in CANONICAL_HOOK_IDS:
            entry = str(hook.get("entry", ""))
            expected = expected_entries.get(str(hook_id), "")
            if entry != expected:
                return PrecommitSignal.NON_CANONICAL

    return PrecommitSignal.COMPLETE


def observed_precommit_mode(
    target: Path, package: str | None = None
) -> InstallMode | None:
    """Infer the install mode the deployed hook entries are shaped for.

    Reads ``.pre-commit-config.yaml`` and inspects the canonical hook entries.
    Each mode renders a distinct entry prefix (``uv run --no-sync
    vaultspec-core`` for dependency mode, ``uvx --from vaultspec-core
    vaultspec-core`` for tool mode), so the prefix a deployed entry carries
    names the mode it was provisioned for. The prefixes are read from
    :func:`~vaultspec_core.core.commands.entry_prefix_for_mode`, the same source
    the renderer uses, so this never hardcodes a second copy of the shape.

    The pre-commit hooks are core's own artifact: they invoke ``vaultspec-core``
    regardless of which companion packages are provisioned, and a companion
    package scaffolds no hooks of its own. So for any *package* other than
    ``vaultspec-core`` this observes nothing (``None``) - that package's mode is
    observable only through its MCP launch, not through hooks it does not own.

    Args:
        target: Workspace root directory.
        package: Distribution name whose observed hook shape to read; ``None``
            means ``vaultspec-core``. Any other package returns ``None``.

    Returns:
        The single :class:`~vaultspec_core.core.enums.InstallMode` every
        canonical hook entry agrees on, or ``None`` when there is no config, no
        canonical hook, the entries disagree, or *package* is not core.
    """
    from ..commands import CANONICAL_HOOK_IDS, entry_prefix_for_mode
    from ..enums import InstallMode
    from ..workspace_mode import CORE_DISTRIBUTION_NAME, canonical_distribution_name

    pkg = package if package is not None else CORE_DISTRIBUTION_NAME
    if canonical_distribution_name(pkg) != CORE_DISTRIBUTION_NAME:
        return None

    local_hooks = _local_precommit_hooks(target / ".pre-commit-config.yaml")
    if local_hooks is None:
        return None

    # Longest prefix first so tool mode's "uvx --from vaultspec-core
    # vaultspec-core" is tested before any shorter prefix could partial-match.
    prefixes = sorted(
        ((entry_prefix_for_mode(m), m) for m in InstallMode),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )

    observed: set[InstallMode] = set()
    for hook in local_hooks:
        if hook.get("id") not in CANONICAL_HOOK_IDS:
            continue
        entry = str(hook.get("entry", ""))
        for prefix, mode in prefixes:
            if entry.startswith(prefix):
                observed.add(mode)
                break

    if len(observed) == 1:
        return next(iter(observed))
    return None
