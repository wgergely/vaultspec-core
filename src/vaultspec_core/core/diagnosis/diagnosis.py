"""Dataclasses aggregating diagnostic signals for providers and workspaces.

The :func:`diagnose` orchestrator drives layered signal collection, delegating
to the individual collectors in :mod:`.collectors`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..enums import InstallMode, Tool
from ..home import ProcessRegistryDiagnosis, ProcessRegistrySignal
from .signals import (
    BuiltinVersionSignal,
    ConfigSignal,
    ContentSignal,
    FrameworkSignal,
    GitattributesSignal,
    GitignoreSignal,
    ManifestEntrySignal,
    ModeMismatchSignal,
    PrecommitSignal,
    ProviderDirSignal,
    RenameIntegritySignal,
    VaultContentSignal,
    VersionFloorSignal,
)

if TYPE_CHECKING:
    from .collectors_companion import CompanionCapability

logger = logging.getLogger(__name__)


@dataclass
class PackageModeDiagnosis:
    """Per-package install-mode and version-floor diagnosis.

    One entry per distribution declared in the shared
    ``.vaultspec/workspace.json`` map, so the doctor can render an install-mode
    row (and, when a floor is violated, a version-floor row) for each provisioned
    package independently rather than only for core. A mixed configuration (core
    in one mode, a companion package in another) produces one of these per
    package, each read against that package's own declared entry and its own
    observed artifacts.

    Args:
        package: The canonicalized distribution name.
        declared_mode: The mode this package's map entry declares. Kept distinct
            from the mode its artifacts render as (``dev`` renders like
            ``dependency``) so the doctor row can label the honest declared
            value.
        mode_mismatch: Coherence between the declared mode and the observed
            artifact shapes for this package.
        version_floor: State of this package's running version against its own
            declared floor.
        version_floor_running: Running version string, populated only when
            ``version_floor`` is ``BELOW``.
        version_floor_minimum: Declared floor string, populated only when
            ``version_floor`` is ``BELOW``.
    """

    package: str
    declared_mode: InstallMode
    mode_mismatch: ModeMismatchSignal
    version_floor: VersionFloorSignal
    version_floor_running: str = ""
    version_floor_minimum: str = ""


@dataclass
class ProviderDiagnosis:
    """Collected diagnostic signals for a single provider.

    Args:
        tool: The :class:`~vaultspec_core.core.enums.Tool` being diagnosed.
        dir_state: Observed state of the provider directory.
        manifest_entry: Coherence between directory and manifest.
        content: Per-resource :class:`ContentSignal` map.
        config: State of the provider's root configuration.
    """

    tool: Tool
    dir_state: ProviderDirSignal
    manifest_entry: ManifestEntrySignal
    content: dict[str, ContentSignal] = field(default_factory=dict)
    # Neutral by default because framework-only and corrupted-framework
    # diagnosis paths do not collect provider config state. Callers that
    # actually inspect configs must pass the collected signal explicitly.
    config: ConfigSignal = ConfigSignal.OK


@dataclass
class HomeDiagnosis:
    """Non-provider diagnostics that may carry structured detail."""

    process_registry: ProcessRegistryDiagnosis = field(
        default_factory=lambda: ProcessRegistryDiagnosis(ProcessRegistrySignal.ABSENT)
    )
    divergent_projections: list[str] = field(default_factory=list)
    #: Observed provisioning state of the semantic-search companion package,
    #: or ``None`` when the probe was not run for this scope. Reports
    #: provisioning only - never liveness; the capability names the companion
    #: command that answers health.
    companion: CompanionCapability | None = None


@dataclass
class WorkspaceDiagnosis:
    """Top-level diagnosis aggregating framework and provider states.

    Args:
        framework: Observed state of the vaultspec framework directory.
        providers: Per-tool :class:`ProviderDiagnosis` map.
        builtin_version: Version state of built-in resource snapshots.
        gitignore: Observed state of gitignore entries.
        migration_status: Schema-migration status string. ``"up_to_date"``
            when the manifest version covers every registered migration,
            ``"pending"`` when one or more migrations have a target
            version above the manifest, ``"unknown"`` when the workspace
            has no manifest.
        pending_migrations: List of pending migration names; empty
            unless ``migration_status`` is ``"pending"``.
        vault_content: Read-only generated annotation state for ``.vault/``.
            vault_annotation_count: Count of markdown documents containing
            generated template annotations.
        vault_unreadable_count: Count of unreadable markdown documents skipped
            by the annotation probe.
        rename_integrity: Observed state of name/filename mismatches.
        rename_mismatch_count: Count of name/filename mismatches.
        mode_mismatch: Coherence between core's persisted install-mode
            declaration and the shape of core's provisioned hook and MCP
            artifacts. This is core's own view, kept for the resolver's install
            and sync plans; the per-package ``packages`` map below carries the
            same axis for every declared package including core.
        version_floor: State of core's running version against core's committed
            floor constraint.
        version_floor_running: Running version string, populated only when
            ``version_floor`` is ``BELOW``.
        version_floor_minimum: Declared floor string, populated only when
            ``version_floor`` is ``BELOW``.
        stale_mcp_seeds: Server names of package-bundled MCP seed definitions
            still in a static pre-mode shape; core cannot refresh these, only
            the owning package's installer can.
        packages: Per-package install-mode and version-floor diagnosis, one
            :class:`PackageModeDiagnosis` per distribution declared in the shared
            workspace map, keyed by canonicalized distribution name. Empty when
            no ``workspace.json`` declaration exists. Drives the doctor's
            per-package install-mode and version-floor rows.
        divergent_projections: Workspace-relative paths of projected provider
            files whose on-disk content differs from what the sync engine would
            write. Populated only when ``framework`` is
            :attr:`~vaultspec_core.core.diagnosis.signals.FrameworkSignal.ADOPTABLE`,
            where it names the content an adopting run would destroy.
        home: Structured Core-home and adoption diagnostics.
    """

    framework: FrameworkSignal
    providers: dict[Tool, ProviderDiagnosis] = field(default_factory=dict)
    builtin_version: BuiltinVersionSignal = BuiltinVersionSignal.NO_SNAPSHOTS
    gitignore: GitignoreSignal = GitignoreSignal.NO_FILE
    gitattributes: GitattributesSignal = GitattributesSignal.NO_FILE
    mcp: ConfigSignal = ConfigSignal.MISSING
    precommit: PrecommitSignal = PrecommitSignal.NO_FILE
    stale_mcp_seeds: list[str] = field(default_factory=list)
    migration_status: str = "up_to_date"
    pending_migrations: list[str] = field(default_factory=list)
    vault_content: VaultContentSignal = VaultContentSignal.NO_VAULT
    vault_annotation_count: int = 0
    vault_unreadable_count: int = 0
    rename_integrity: RenameIntegritySignal = RenameIntegritySignal.CLEAN
    rename_mismatch_count: int = 0
    mode_mismatch: ModeMismatchSignal = ModeMismatchSignal.CLEAN
    version_floor: VersionFloorSignal = VersionFloorSignal.OK
    version_floor_running: str = ""
    version_floor_minimum: str = ""
    packages: dict[str, PackageModeDiagnosis] = field(default_factory=dict)
    home: HomeDiagnosis = field(default_factory=HomeDiagnosis)

    @property
    def divergent_projections(self) -> list[str]:
        """Workspace projections an adopting run would overwrite."""
        return self.home.divergent_projections

    @divergent_projections.setter
    def divergent_projections(self, value: list[str]) -> None:
        self.home.divergent_projections = value

    @property
    def process_registry(self) -> ProcessRegistryDiagnosis:
        """Machine-global process-registry diagnosis."""
        return self.home.process_registry


def _safe_framework_presence(target: Path) -> FrameworkSignal:
    """Collect framework presence, neutral to :attr:`FrameworkSignal.MISSING`."""
    from .collectors import collect_framework_presence

    try:
        return collect_framework_presence(target)
    except Exception:
        logger.warning("Framework presence collector failed", exc_info=True)
        return FrameworkSignal.MISSING


def _safe_gitignore_state(target: Path) -> GitignoreSignal:
    """Collect gitignore state, or report that the check could not run.

    A collector that failed has not confirmed anything. It used to answer
    :attr:`GitignoreSignal.UNMANAGED` - "there is no block" - which is a claim
    about the file, made by a check that never read it. #399 introduced
    ``UNMANAGED`` for exactly this fallback; splitting :attr:`UNREADABLE` out of
    it keeps the weighing while making the row honest about which of the two it
    observed (issue #407).
    """
    from .collectors import collect_gitignore_state

    try:
        return collect_gitignore_state(target)
    except Exception:
        logger.warning("Gitignore state collector failed", exc_info=True)
        return GitignoreSignal.UNREADABLE


def _safe_gitattributes_state(target: Path) -> GitattributesSignal:
    """Collect gitattributes state, or report that the check could not run.

    ``NO_FILE`` said the file was absent. An undecodable ``.gitattributes`` is
    very much present, and reporting its absence is what let ``doctor`` read
    ``info no_file`` while ``install --force`` died on the same bytes
    (issue #407).
    """
    from .collectors import collect_gitattributes_state

    try:
        return collect_gitattributes_state(target)
    except Exception:
        logger.warning("Gitattributes state collector failed", exc_info=True)
        return GitattributesSignal.UNREADABLE


def _safe_mcp_config_state(target: Path) -> ConfigSignal:
    """Collect MCP config state, or report that the check could not run.

    ``MISSING`` said the file was absent. A collector that failed has not
    established that, and reporting it let the row read benign while `sync`
    refused the same workspace (issue #407).
    """
    from .collectors import collect_mcp_config_state

    try:
        return collect_mcp_config_state(target)
    except Exception:
        logger.warning("MCP config state collector failed", exc_info=True)
        return ConfigSignal.UNREADABLE


def _safe_precommit_state(target: Path) -> PrecommitSignal:
    """Collect pre-commit state, or report that the check could not run.

    ``NO_FILE`` is the benign reading for a workspace with no
    ``.pre-commit-config.yaml``. A workspace whose config exists but cannot be
    parsed - or whose ``workspace.json`` is corrupt, which fails this collector
    on the way in - is not that workspace, and saying so let ``doctor`` exit
    ``0`` while every mutating verb refused the same tree (issue #407).
    """
    from .collectors import collect_precommit_state

    try:
        return collect_precommit_state(target)
    except Exception:
        logger.warning("Precommit state collector failed", exc_info=True)
        return PrecommitSignal.UNREADABLE


def _safe_stale_mcp_seeds(target: Path) -> list[str]:
    """Collect stale MCP seed names, neutral to an empty list."""
    from .collectors import collect_stale_seed_definitions

    try:
        return collect_stale_seed_definitions(target)
    except Exception:
        logger.warning("Stale MCP seed collector failed", exc_info=True)
        return []


def _safe_vault_content_state(
    target: Path,
) -> tuple[VaultContentSignal, int, int]:
    """Collect vault annotation state, neutral to ``(NO_VAULT, 0, 0)``."""
    from .collectors import collect_vault_content_state

    try:
        return collect_vault_content_state(target)
    except Exception:
        logger.warning("Vault content collector failed", exc_info=True)
        return VaultContentSignal.NO_VAULT, 0, 0


def _safe_rename_integrity(target: Path) -> tuple[RenameIntegritySignal, int]:
    """Collect rename integrity, neutral to ``(ERROR, 0)`` on failure."""
    from .collectors import collect_rename_integrity

    try:
        return collect_rename_integrity(target)
    except Exception:
        logger.warning("Rename integrity collector failed", exc_info=True)
        return RenameIntegritySignal.ERROR, 0


def _safe_mode_mismatch_state(
    target: Path, *, package: str | None = None
) -> ModeMismatchSignal:
    """Collect mode-mismatch state for *package* (``None`` means core).

    A failed probe is neutral (:attr:`ModeMismatchSignal.CLEAN`), never a
    crash, matching the other always-collected signals.
    """
    from .collectors import collect_mode_mismatch_state

    try:
        return collect_mode_mismatch_state(target, package=package)
    except Exception:
        if package is None:
            logger.warning("Mode mismatch collector failed", exc_info=True)
        else:
            logger.warning(
                "Mode mismatch collector failed for %s", package, exc_info=True
            )
        return ModeMismatchSignal.CLEAN


def _safe_companion_capability(target: Path) -> CompanionCapability | None:
    """Probe the semantic-search companion's provisioning state.

    Returns ``None`` only when the probe itself fails, which is distinct from
    the companion being absent - absence is a reported state, not a missing
    answer. The probe is a total local function over two file reads, so this
    guard should never fire; it exists so a diagnosis surface can never be
    taken down by the newest collector on it.
    """
    from .collectors_companion import collect_companion_capability

    try:
        return collect_companion_capability(target)
    except Exception:
        logger.warning("Companion capability probe failed", exc_info=True)
        return None


def _safe_version_floor_state(
    target: Path, *, package: str | None = None
) -> tuple[VersionFloorSignal, str, str]:
    """Collect the version-floor state for *package* (``None`` means core).

    Floor constraints are reported (not enforced) here: doctor surfaces a
    below-floor workspace without raising, sharing the resolver's comparator.
    """
    from .collectors import collect_version_floor_state

    try:
        return collect_version_floor_state(target, package=package)
    except Exception:
        if package is None:
            logger.warning("Version floor collector failed", exc_info=True)
        else:
            logger.warning(
                "Version floor collector failed for %s", package, exc_info=True
            )
        return VersionFloorSignal.OK, "", ""


def _safe_manifest_coherence(target: Path) -> dict[str, ManifestEntrySignal]:
    """Collect manifest coherence, neutral to an empty map."""
    from .collectors import collect_manifest_coherence

    try:
        return collect_manifest_coherence(target)
    except Exception:
        logger.warning("Manifest coherence collector failed", exc_info=True)
        return {}


def _safe_builtin_version_state(target: Path) -> BuiltinVersionSignal:
    """Collect built-in version state, neutral to ``NO_SNAPSHOTS``."""
    from .collectors import collect_builtin_version_state

    try:
        return collect_builtin_version_state(target)
    except Exception:
        logger.warning("Builtin version collector failed", exc_info=True)
        return BuiltinVersionSignal.NO_SNAPSHOTS


def _safe_migration_status(target: Path) -> tuple[str, list[str]]:
    """Collect migration status, neutral to ``("up_to_date", [])``."""
    from ...migrations import migration_status

    try:
        status, pending_names = migration_status(target)
        return status.value, list(pending_names)
    except Exception:
        logger.warning("Migration status collector failed", exc_info=True)
        return "up_to_date", []


def _safe_provider_dir_state_quiet(target: Path, tool_value: str) -> ProviderDirSignal:
    """Collect provider directory state without logging (partial diagnosis path)."""
    from .collectors import collect_provider_dir_state

    try:
        return collect_provider_dir_state(target, tool_value)
    except Exception:
        return ProviderDirSignal.MISSING


def _safe_provider_dir_state(target: Path, tool_value: str) -> ProviderDirSignal:
    """Collect provider directory state, neutral to ``MISSING``."""
    from .collectors import collect_provider_dir_state

    try:
        return collect_provider_dir_state(target, tool_value)
    except Exception:
        logger.warning(
            "Provider dir collector failed for %s", tool_value, exc_info=True
        )
        return ProviderDirSignal.MISSING


def _safe_config_state(tool_value: str) -> ConfigSignal:
    """Collect provider config state, neutral to ``MISSING``."""
    from .collectors import collect_config_state

    try:
        return collect_config_state(tool_value)
    except Exception:
        logger.warning(
            "Config state collector failed for %s", tool_value, exc_info=True
        )
        return ConfigSignal.MISSING


def _safe_content_integrity(tool_value: str) -> dict[str, ContentSignal]:
    """Collect content integrity, neutral to an empty map."""
    from .collectors import collect_content_integrity

    try:
        return collect_content_integrity(tool_value)
    except Exception:
        logger.warning(
            "Content integrity collector failed for %s", tool_value, exc_info=True
        )
        return {}


def _collect_package_diagnoses(target: Path) -> dict[str, PackageModeDiagnosis]:
    """Collect per-package install-mode and version-floor diagnosis.

    One entry per distribution declared in the shared workspace map, each read
    against its own entry. The top-level ``mode_mismatch``/``version_floor``
    stay core's own view (the resolver reads them); this map drives the
    doctor's per-package rows and covers companion packages core's view cannot
    represent.
    """
    from ..workspace_mode import read_package_declarations

    try:
        declared_packages = read_package_declarations(target)
    except Exception:
        logger.warning("Package declarations read failed", exc_info=True)
        declared_packages = {}

    package_diags: dict[str, PackageModeDiagnosis] = {}
    for pkg_name, pkg_decl in sorted(declared_packages.items()):
        pkg_floor, pkg_floor_running, pkg_floor_minimum = _safe_version_floor_state(
            target, package=pkg_name
        )
        package_diags[pkg_name] = PackageModeDiagnosis(
            package=pkg_name,
            declared_mode=pkg_decl.install_mode,
            mode_mismatch=_safe_mode_mismatch_state(target, package=pkg_name),
            version_floor=pkg_floor,
            version_floor_running=pkg_floor_running,
            version_floor_minimum=pkg_floor_minimum,
        )
    return package_diags


def _collect_layer1_diagnosis(
    target: Path, scope: str, core_home: Path | None
) -> WorkspaceDiagnosis:
    """Collect the always-on layer 1 signals plus the per-package map.

    Runs independently of framework presence, so the returned
    :class:`WorkspaceDiagnosis` is populated even when the framework directory
    is missing or corrupted.
    """
    vault_content, vault_annotation_count, vault_unreadable_count = (
        _safe_vault_content_state(target)
    )

    rename_integrity = RenameIntegritySignal.CLEAN
    rename_mismatch_count = 0
    if scope == "full":
        rename_integrity, rename_mismatch_count = _safe_rename_integrity(target)

    version_floor, version_floor_running, version_floor_minimum = (
        _safe_version_floor_state(target)
    )

    from ..home import diagnose_process_registry

    process_registry = diagnose_process_registry(core_home)
    companion = _safe_companion_capability(target) if scope == "full" else None
    return WorkspaceDiagnosis(
        framework=_safe_framework_presence(target),
        gitignore=_safe_gitignore_state(target),
        gitattributes=_safe_gitattributes_state(target),
        mcp=_safe_mcp_config_state(target),
        precommit=_safe_precommit_state(target),
        stale_mcp_seeds=_safe_stale_mcp_seeds(target),
        vault_content=vault_content,
        vault_annotation_count=vault_annotation_count,
        vault_unreadable_count=vault_unreadable_count,
        rename_integrity=rename_integrity,
        rename_mismatch_count=rename_mismatch_count,
        mode_mismatch=_safe_mode_mismatch_state(target),
        version_floor=version_floor,
        version_floor_running=version_floor_running,
        version_floor_minimum=version_floor_minimum,
        packages=_collect_package_diagnoses(target),
        home=HomeDiagnosis(process_registry=process_registry, companion=companion),
    )


def _diagnose_corrupted_or_adoptable(
    target: Path, diag: WorkspaceDiagnosis
) -> WorkspaceDiagnosis:
    """Collect the partial diagnosis for a corrupted or adoptable framework.

    The manifest may be broken or intentionally absent but directories may
    still exist, so this collects what it can without requiring a valid
    WorkspaceContext.
    """
    from .collectors import collect_divergent_projections

    manifest_map = _safe_manifest_coherence(target)
    for tool in Tool:
        entry = manifest_map.get(tool.value, ManifestEntrySignal.NOT_INSTALLED)
        diag.providers[tool] = ProviderDiagnosis(
            tool=tool,
            dir_state=_safe_provider_dir_state_quiet(target, tool.value),
            manifest_entry=entry,
        )

    # Adoption is the one path that claims a workspace vaultspec has never
    # written to locally, so it is the one path that must name what it would
    # overwrite before it writes anything. A corrupt manifest is a different
    # condition and keeps its existing repair semantics.
    if diag.framework == FrameworkSignal.ADOPTABLE:
        try:
            diag.divergent_projections = collect_divergent_projections(target)
        except Exception:
            logger.warning("Divergent projection collector failed", exc_info=True)
    return diag


def _diagnose_framework_scope(
    diag: WorkspaceDiagnosis, manifest_map: dict[str, ManifestEntrySignal]
) -> WorkspaceDiagnosis:
    """Build minimal provider entries from manifest data only."""
    for tool in Tool:
        entry = manifest_map.get(tool.value, ManifestEntrySignal.NOT_INSTALLED)
        diag.providers[tool] = ProviderDiagnosis(
            tool=tool,
            dir_state=ProviderDirSignal.MISSING,
            manifest_entry=entry,
        )
    return diag


def _diagnose_providers_full_or_sync(
    target: Path,
    diag: WorkspaceDiagnosis,
    manifest_map: dict[str, ManifestEntrySignal],
    scope: str,
) -> WorkspaceDiagnosis:
    """Collect per-provider details for ``"full"`` or ``"sync"`` scope."""
    for tool in Tool:
        entry = manifest_map.get(tool.value, ManifestEntrySignal.NOT_INSTALLED)

        if entry == ManifestEntrySignal.NOT_INSTALLED:
            diag.providers[tool] = ProviderDiagnosis(
                tool=tool,
                dir_state=ProviderDirSignal.MISSING,
                manifest_entry=entry,
            )
            continue

        content: dict[str, ContentSignal] = {}
        if scope == "full":
            # Layer 4: full scope only - content integrity
            content = _safe_content_integrity(tool.value)

        diag.providers[tool] = ProviderDiagnosis(
            tool=tool,
            dir_state=_safe_provider_dir_state(target, tool.value),
            manifest_entry=entry,
            content=content,
            config=_safe_config_state(tool.value),
        )

    return diag


def diagnose(
    target: Path, *, scope: str = "full", core_home: Path | None = None
) -> WorkspaceDiagnosis:
    """Run layered diagnostic collection against a workspace.

    Args:
        target: Workspace root directory to diagnose.
        scope: Collection depth - ``"full"`` runs all collectors (doctor
            command), ``"framework"`` runs only framework presence and manifest
            coherence (install), ``"sync"`` adds provider dir, config, and
            gitignore checks.
        core_home: Explicit machine-global Core home for isolated callers.

    Returns:
        Populated :class:`WorkspaceDiagnosis` instance.
    """
    valid_scopes = frozenset({"full", "framework", "sync"})
    if scope not in valid_scopes:
        raise ValueError(
            f"Invalid scope '{scope}'. Valid: {', '.join(sorted(valid_scopes))}"
        )

    # Layer 1: always collected, independent of framework presence.
    diag = _collect_layer1_diagnosis(target, scope, core_home)

    if diag.framework == FrameworkSignal.MISSING:
        return diag

    if diag.framework in (FrameworkSignal.CORRUPTED, FrameworkSignal.ADOPTABLE):
        return _diagnose_corrupted_or_adoptable(target, diag)

    # Layer 2: framework is PRESENT - collect manifest and builtin state
    manifest_map = _safe_manifest_coherence(target)
    diag.builtin_version = _safe_builtin_version_state(target)
    diag.migration_status, diag.pending_migrations = _safe_migration_status(target)

    if scope == "framework":
        return _diagnose_framework_scope(diag, manifest_map)

    # Layer 3: scope is "full" or "sync" - collect per-provider details
    return _diagnose_providers_full_or_sync(target, diag, manifest_map, scope)
