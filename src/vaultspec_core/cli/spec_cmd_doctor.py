"""``vaultspec-core spec doctor`` - diagnose workspace health.

Defines :func:`cmd_doctor`, mounted by :mod:`vaultspec_core.cli.spec_cmd`
as the ``doctor`` command on :data:`~vaultspec_core.cli.spec_cmd_app.spec_app`.
Also hosts the diagnosis-table rendering and exit-code helpers, some of
which (:func:`doctor_exit_code`, :func:`render_diagnosis_table`) are
re-exported from :mod:`vaultspec_core.cli.spec_cmd` for use by tests and
:mod:`vaultspec_core.cli.root`.
"""

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated

import typer

from vaultspec_core.cli._target import (
    TargetOption,
    apply_target,
    resolve_effective_target,
)
from vaultspec_core.cli.spec_cmd_shared import emit_json

if TYPE_CHECKING:
    from rich.console import Console

    from vaultspec_core.core.diagnosis import (
        GitattributesSignal,
        GitignoreSignal,
        ProviderDiagnosis,
        WorkspaceDiagnosis,
    )

__all__ = [
    "cmd_doctor",
    "doctor_exit_code",
    "logger",
    "render_diagnosis_table",
]

logger = logging.getLogger(__name__)


def cmd_doctor(
    target: TargetOption = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output diagnosis as JSON")
    ] = False,
    gate_errors: Annotated[
        bool,
        typer.Option(
            "--gate-errors",
            help=(
                "Exit 0 on warnings; fail (exit 2) only on errors. For the "
                "pre-commit gate, where warning-level provider-mirror lag is an "
                "expected steady state that must not block commits."
            ),
        ),
    ] = False,
) -> None:
    """Diagnose workspace health and report issues.

    Runs all diagnostic collectors and reports the state of the framework,
    providers, builtins, gitignore, and configuration files.

    Exit codes: 0 = all ok, 1 = warnings, 2 = errors. With ``--gate-errors``
    the warning exit is folded to 0 so only errors (exit 2) fail; the report
    is unchanged and still lists every warning.
    """
    import dataclasses

    from vaultspec_core.core.diagnosis import (
        diagnose,
    )

    effective = resolve_effective_target(target)

    if not effective.exists():
        typer.echo(
            f"Error: target directory does not exist: {effective}",
            err=True,
        )
        raise typer.Exit(code=2)

    previous_logging_disable = logging.root.manager.disable
    if json_output:
        logging.disable(logging.CRITICAL)
    try:
        # Initialize workspace context so collectors can read tool configs.
        try:
            apply_target(target)
        except Exception:
            logger.debug("Could not initialize workspace context", exc_info=True)

        try:
            diag = diagnose(effective, scope="full")
        except Exception as exc:
            typer.echo(f"Error: diagnosis failed: {exc}", err=True)
            raise typer.Exit(code=2) from None
    finally:
        if json_output:
            logging.disable(previous_logging_disable)

    if json_output:
        data = dataclasses.asdict(diag)
        exit_code = doctor_exit_code(diag)
        gated = _gate(exit_code, gate_errors=gate_errors)
        emit_json("spec.doctor", "failed" if gated else "unchanged", data)
        raise typer.Exit(code=gated)

    from vaultspec_core.console import get_console

    console = get_console()
    render_diagnosis_table(console, diag)

    exit_code = doctor_exit_code(diag)
    raise typer.Exit(code=_gate(exit_code, gate_errors=gate_errors))


def _append_companion_row(
    rows: list[dict[str, object]], diag: "WorkspaceDiagnosis"
) -> None:
    """Append the semantic-search row, when the probe ran.

    Never error-weighted. Every state this row reports is either an ordinary
    fact about how the workspace is provisioned or, at worst, an advisory - so
    it must not move the doctor's exit code. Core has no standing to fail a run
    over a package it does not depend on.

    The row always names the companion's own health command, because the probe
    reports provisioning and not liveness. Saying so on every row is the whole
    guard against the one failure mode this design can still produce: a
    provisioned-but-dead companion reading as fine.
    """
    from vaultspec_core.cli.rendering import Cell
    from vaultspec_core.core.diagnosis.collectors_companion import CompanionSignal

    cap = diag.home.companion
    if cap is None:
        return

    mode_note = f", {cap.mode.value} mode" if cap.mode is not None else ""
    detail = {
        CompanionSignal.ABSENT: (
            f"{cap.package} not provisioned; core discovery and find cover "
            f"document lookup without it"
        ),
        CompanionSignal.DECLARED: (
            f"{cap.package} provisioned{mode_note}; version not visible from "
            f"here - check liveness with {cap.health_authority}"
        ),
        CompanionSignal.PRESENT: (
            f"{cap.package} {cap.version} provisioned{mode_note}; "
            f"check liveness with {cap.health_authority}"
        ),
        CompanionSignal.BELOW_FLOOR: (
            f"{cap.package} {cap.version} is below the advisory floor "
            f"{cap.floor}; upgrade with uv tool upgrade {cap.package} "
            f"(advisory only - core does not depend on it)"
        ),
    }.get(cap.signal, str(cap.signal))

    status, style = {
        CompanionSignal.ABSENT: ("none", "dim"),
        CompanionSignal.DECLARED: ("ok", "green"),
        CompanionSignal.PRESENT: ("ok", "green"),
        CompanionSignal.BELOW_FLOOR: ("warn", "yellow"),
    }.get(cap.signal, ("none", "dim"))

    rows.append(
        {
            "component": "semantic search",
            "status": Cell(status, style=style),
            "detail": detail,
        }
    )


def render_diagnosis_table(_console: "Console", diag: "WorkspaceDiagnosis") -> None:
    """Render the workspace diagnosis as a box-free listing.

    The ``_console`` argument is retained for call-site compatibility; the
    listing renderer resolves the shared console itself.
    """
    from vaultspec_core.cli.rendering import Cell, Column, render_listing
    from vaultspec_core.core.diagnosis import (
        BuiltinVersionSignal,
        ConfigSignal,
        ContentSignal,
        FrameworkSignal,
        GitattributesSignal,
        GitignoreSignal,
        ManifestEntrySignal,
        ModeMismatchSignal,
        PrecommitSignal,
        ProcessRegistrySignal,
        RenameIntegritySignal,
        VaultContentSignal,
        VersionFloorSignal,
    )

    rows: list[dict[str, object]] = []

    # Framework row
    fw_status, fw_style = _signal_status(
        diag.framework,
        {
            FrameworkSignal.PRESENT: ("ok", "green"),
            FrameworkSignal.MISSING: ("error", "red"),
            FrameworkSignal.CORRUPTED: ("error", "red"),
            FrameworkSignal.ADOPTABLE: ("warn", "yellow"),
        },
    )
    fw_detail = {
        FrameworkSignal.PRESENT: ".vaultspec/ present",
        FrameworkSignal.MISSING: ".vaultspec/ not found",
        FrameworkSignal.CORRUPTED: ".vaultspec/ corrupted manifest",
        FrameworkSignal.ADOPTABLE: (
            ".vaultspec/ present, no runtime manifest - run install to adopt"
        ),
    }.get(diag.framework, str(diag.framework))
    rows.append(
        {
            "component": "framework",
            "status": Cell(fw_status, style=fw_style),
            "detail": fw_detail,
        }
    )

    process_status, process_style = _signal_status(
        diag.process_registry.signal,
        {
            ProcessRegistrySignal.ABSENT: ("info", "dim"),
            ProcessRegistrySignal.HEALTHY: ("ok", "green"),
            ProcessRegistrySignal.STALE: ("warn", "yellow"),
        },
    )
    process_detail = {
        ProcessRegistrySignal.ABSENT: "~/.vaultspec/procs/ not present",
        ProcessRegistrySignal.HEALTHY: (
            f"{diag.process_registry.record_count} process record(s); "
            "all recorded PIDs alive"
        ),
        ProcessRegistrySignal.STALE: (
            f"{len(diag.process_registry.stale_records)} stale of "
            f"{diag.process_registry.record_count} process record(s): "
            + ", ".join(diag.process_registry.stale_records)
        ),
    }.get(diag.process_registry.signal, str(diag.process_registry.signal))
    rows.append(
        {
            "component": "process registry",
            "status": Cell(process_status, style=process_style),
            "detail": process_detail,
        }
    )

    # Provider rows
    for tool, prov in diag.providers.items():
        prov_status, prov_style = _provider_status(prov)
        details: list[str] = []
        details.append(f"dir: {prov.dir_state.value}")
        if prov.manifest_entry not in (
            ManifestEntrySignal.COHERENT,
            ManifestEntrySignal.NOT_INSTALLED,
        ):
            details.append(f"manifest: {prov.manifest_entry.value}")
        if prov.config not in (ConfigSignal.OK,):
            details.append(f"config: {prov.config.value}")
        stale = sum(1 for s in prov.content.values() if s != ContentSignal.CLEAN)
        if stale:
            details.append(f"{stale} file(s) need attention")
        rows.append(
            {
                "component": tool.value,
                "status": Cell(prov_status, style=prov_style),
                "detail": ", ".join(details),
            }
        )

    # Builtins row
    bv_status, bv_style = _signal_status(
        diag.builtin_version,
        {
            BuiltinVersionSignal.CURRENT: ("ok", "green"),
            BuiltinVersionSignal.MODIFIED: ("warn", "yellow"),
            BuiltinVersionSignal.DELETED: ("error", "red"),
            BuiltinVersionSignal.NO_SNAPSHOTS: ("info", "dim"),
        },
    )
    rows.append(
        {
            "component": "builtins",
            "status": Cell(bv_status, style=bv_style),
            "detail": diag.builtin_version.value,
        }
    )

    # Gitignore row
    gi_status, gi_style = _signal_status(
        diag.gitignore,
        {
            GitignoreSignal.COMPLETE: ("ok", "green"),
            GitignoreSignal.PARTIAL: ("warn", "yellow"),
            GitignoreSignal.UNMANAGED: ("warn", "yellow"),
            GitignoreSignal.UNREADABLE: ("warn", "yellow"),
            GitignoreSignal.NO_ENTRIES: ("info", "dim"),
            GitignoreSignal.NO_FILE: ("info", "dim"),
            GitignoreSignal.CORRUPTED: ("error", "red"),
        },
    )
    # The degraded reading is the one a reader can act on, so it names the act.
    # Without it the row states a condition and no way out of it.
    gi_detail = diag.gitignore.value
    if diag.gitignore == GitignoreSignal.UNMANAGED:
        gi_detail = (
            f"{gi_detail} (install --force to restore, "
            "spec gitignore disable to decline)"
        )
    rows.append(
        {
            "component": "gitignore",
            "status": Cell(gi_status, style=gi_style),
            "detail": gi_detail,
        }
    )

    # Gitattributes row
    ga_status, ga_style = _signal_status(
        diag.gitattributes,
        {
            GitattributesSignal.COMPLETE: ("ok", "green"),
            GitattributesSignal.PARTIAL: ("warn", "yellow"),
            GitattributesSignal.UNMANAGED: ("warn", "yellow"),
            GitattributesSignal.UNREADABLE: ("warn", "yellow"),
            GitattributesSignal.NO_ENTRIES: ("info", "dim"),
            GitattributesSignal.NO_FILE: ("info", "dim"),
            GitattributesSignal.CORRUPTED: ("error", "red"),
        },
    )
    ga_detail = diag.gitattributes.value
    if diag.gitattributes == GitattributesSignal.UNMANAGED:
        ga_detail = (
            f"{ga_detail} (install --force to restore, "
            "spec gitattributes disable to decline)"
        )
    rows.append(
        {
            "component": "gitattributes",
            "status": Cell(ga_status, style=ga_style),
            "detail": ga_detail,
        }
    )

    # MCP row
    mcp_status, mcp_style = _signal_status(
        diag.mcp,
        {
            ConfigSignal.OK: ("ok", "green"),
            ConfigSignal.MISSING: ("warn", "yellow"),
            ConfigSignal.PARTIAL_MCP: ("info", "dim"),
            ConfigSignal.USER_MCP: ("info", "dim"),
            ConfigSignal.FOREIGN: ("info", "dim"),
            ConfigSignal.REGISTRY_DRIFT: ("warn", "yellow"),
            ConfigSignal.UNREADABLE: ("warn", "yellow"),
        },
    )
    mcp_detail = {
        ConfigSignal.OK: ".mcp.json present",
        ConfigSignal.MISSING: ".mcp.json not found",
        ConfigSignal.PARTIAL_MCP: ".mcp.json missing or incomplete",
        ConfigSignal.USER_MCP: ".mcp.json includes user-managed entries",
        ConfigSignal.FOREIGN: ".mcp.json present (no vaultspec entry)",
        ConfigSignal.REGISTRY_DRIFT: ".mcp.json entries differ from registry",
        ConfigSignal.UNREADABLE: ".mcp.json could not be read; this check did not run",
    }.get(diag.mcp, str(diag.mcp))
    rows.append(
        {
            "component": "mcp",
            "status": Cell(mcp_status, style=mcp_style),
            "detail": mcp_detail,
        }
    )

    # Migration row - sourced from the registry collector.
    mig_state = diag.migration_status
    if mig_state == "up_to_date":
        mig_status_label, mig_style = ("ok", "green")
        mig_detail = "all registered migrations applied"
    elif mig_state == "pending":
        mig_status_label, mig_style = ("warn", "yellow")
        pending = ", ".join(diag.pending_migrations)
        mig_detail = f"pending: {pending}"
    else:
        mig_status_label, mig_style = ("info", "dim")
        mig_detail = "no manifest; not installed"
    rows.append(
        {
            "component": "migration",
            "status": Cell(mig_status_label, style=mig_style),
            "detail": mig_detail,
        }
    )

    # Vault content row - read-only annotation signal.
    vc_status, vc_style = _signal_status(
        diag.vault_content,
        {
            VaultContentSignal.CLEAN: ("ok", "green"),
            VaultContentSignal.ANNOTATIONS: ("warn", "yellow"),
            VaultContentSignal.UNREADABLE: ("warn", "yellow"),
            VaultContentSignal.NO_VAULT: ("info", "dim"),
        },
    )
    vc_details = {
        VaultContentSignal.CLEAN: "no generated template annotations",
        VaultContentSignal.ANNOTATIONS: (
            f"{diag.vault_annotation_count} document(s) contain generated "
            "template annotations; run vaultspec-core vault sanitize annotations"
        ),
        VaultContentSignal.UNREADABLE: (
            f"{diag.vault_unreadable_count} markdown file(s) unreadable"
        ),
        VaultContentSignal.NO_VAULT: "no vault documents found",
    }
    vc_detail = vc_details.get(diag.vault_content, str(diag.vault_content))
    if (
        diag.vault_content == VaultContentSignal.ANNOTATIONS
        and diag.vault_unreadable_count
    ):
        vc_detail += f"; {diag.vault_unreadable_count} markdown file(s) unreadable"
    rows.append(
        {
            "component": "vault content",
            "status": Cell(vc_status, style=vc_style),
            "detail": vc_detail,
        }
    )

    # Pre-commit row
    pc_status, pc_style = _signal_status(
        diag.precommit,
        {
            PrecommitSignal.COMPLETE: ("ok", "green"),
            PrecommitSignal.INCOMPLETE: ("warn", "yellow"),
            PrecommitSignal.NON_CANONICAL: ("warn", "yellow"),
            PrecommitSignal.UNREFRESHABLE: ("warn", "yellow"),
            PrecommitSignal.ORPHANED: ("info", "dim"),
            PrecommitSignal.NO_HOOKS: ("warn", "yellow"),
            PrecommitSignal.NOT_INSTALLED: ("warn", "yellow"),
            PrecommitSignal.NO_FILE: ("info", "dim"),
            PrecommitSignal.UNREADABLE: ("warn", "yellow"),
        },
    )
    pc_detail = {
        PrecommitSignal.COMPLETE: "all hooks present in the config",
        PrecommitSignal.INCOMPLETE: "missing canonical hooks",
        PrecommitSignal.NON_CANONICAL: "non-canonical entry pattern",
        PrecommitSignal.UNREFRESHABLE: (
            "prek.toml lacks the vaultspec hooks and sync cannot refresh "
            "them - run 'vaultspec-core spec precommit migrate' to "
            "transplant the canonical entries into prek.toml"
        ),
        PrecommitSignal.ORPHANED: (
            "hooks live in prek.toml; the superseded .pre-commit-config.yaml "
            "is ignored by prek and can be removed ('vaultspec-core spec "
            "precommit migrate --remove-yaml')"
        ),
        PrecommitSignal.NO_HOOKS: "no vaultspec hooks found",
        PrecommitSignal.NOT_INSTALLED: (
            "every hook is configured and none of them runs - git has no "
            "pre-commit hook installed, so a commit executes nothing. Run "
            "'prek install' (or 'pre-commit install') in this checkout"
        ),
        PrecommitSignal.NO_FILE: "no .pre-commit-config.yaml",
        PrecommitSignal.UNREADABLE: ("could not be read; this check did not run"),
    }.get(diag.precommit, str(diag.precommit))
    rows.append(
        {
            "component": "precommit",
            "status": Cell(pc_status, style=pc_style),
            "detail": pc_detail,
        }
    )

    # Stale package-bundled MCP seed advisory (warn-only): core cannot refresh
    # these; only the owning package's installer can.
    if diag.stale_mcp_seeds:
        names = ", ".join(diag.stale_mcp_seeds)
        rows.append(
            {
                "component": "mcp seeds",
                "status": Cell("warn", style="yellow"),
                "detail": (
                    f"stale package seed definition(s): {names} - re-run that "
                    "package's installer with --upgrade to refresh the seed"
                ),
            }
        )

    # Rename integrity row
    ri_status, ri_style = _signal_status(
        diag.rename_integrity,
        {
            RenameIntegritySignal.CLEAN: ("ok", "green"),
            RenameIntegritySignal.MISMATCH: ("warn", "yellow"),
            RenameIntegritySignal.ERROR: ("error", "red"),
        },
    )
    ri_details = {
        RenameIntegritySignal.CLEAN: (
            "all rules, skills, and agents names are consistent"
        ),
        RenameIntegritySignal.MISMATCH: (
            f"{diag.rename_mismatch_count} name/filename mismatch(es) found; "
            "run vaultspec-core vault check rename-integrity"
        ),
        RenameIntegritySignal.ERROR: "failed to evaluate name/filename integrity",
    }
    ri_detail = ri_details.get(diag.rename_integrity, str(diag.rename_integrity))
    rows.append(
        {
            "component": "rename integrity",
            "status": Cell(ri_status, style=ri_style),
            "detail": ri_detail,
        }
    )

    # Install-mode coherence rows: the persisted declaration versus the shape of
    # the provisioned hook and MCP artifacts, one row per declared package. Each
    # labels the honest declared mode (dev stays dev even though it renders like
    # dependency) and flags whether that package's artifacts match. A floor row
    # follows a package only when its running version is below its declared
    # minimum. A workspace with no packages map (legacy, pre-install-mode) falls
    # back to a single informational row from core's own view.
    mode_map = {
        ModeMismatchSignal.CLEAN: ("ok", "green"),
        ModeMismatchSignal.MISMATCH: ("warn", "yellow"),
        ModeMismatchSignal.UNKNOWN: ("info", "dim"),
    }
    if diag.packages:
        for pkg_name, pkg_diag in sorted(diag.packages.items()):
            pm_status, pm_style = _signal_status(pkg_diag.mode_mismatch, mode_map)
            declared = pkg_diag.declared_mode.value
            if pkg_diag.mode_mismatch == ModeMismatchSignal.MISMATCH:
                pm_detail = (
                    f"declared {declared}; hook entries or MCP command do not "
                    "match; run vaultspec-core install --upgrade, or install "
                    "--mode to re-provision"
                )
            else:
                pm_detail = f"declared {declared}; artifacts match"
            rows.append(
                {
                    "component": f"install mode ({pkg_name})",
                    "status": Cell(pm_status, style=pm_style),
                    "detail": pm_detail,
                }
            )
            if pkg_diag.version_floor == VersionFloorSignal.BELOW:
                rows.append(
                    {
                        "component": f"version floor ({pkg_name})",
                        "status": Cell("error", style="red"),
                        "detail": (
                            f"running {pkg_diag.version_floor_running} is below "
                            f"the declared floor {pkg_diag.version_floor_minimum}; "
                            f"upgrade with uv tool upgrade {pkg_name}"
                        ),
                    }
                )
    else:
        mm_status, mm_style = _signal_status(diag.mode_mismatch, mode_map)
        mm_detail = {
            ModeMismatchSignal.CLEAN: "artifacts match the declared install mode",
            ModeMismatchSignal.MISMATCH: (
                "hook entries or MCP command do not match the declared mode; "
                "run vaultspec-core install --upgrade, or install --mode to "
                "re-provision"
            ),
            ModeMismatchSignal.UNKNOWN: "no install mode declared (legacy workspace)",
        }.get(diag.mode_mismatch, str(diag.mode_mismatch))
        rows.append(
            {
                "component": "install mode",
                "status": Cell(mm_status, style=mm_style),
                "detail": mm_detail,
            }
        )
        if diag.version_floor == VersionFloorSignal.BELOW:
            rows.append(
                {
                    "component": "version floor",
                    "status": Cell("error", style="red"),
                    "detail": (
                        f"running {diag.version_floor_running} is below the declared "
                        f"floor {diag.version_floor_minimum}; upgrade with "
                        f"uv tool upgrade vaultspec-core"
                    ),
                }
            )

    _append_companion_row(rows, diag)

    render_listing(
        rows,
        [Column("component"), Column("status"), Column("detail")],
        title="workspace diagnosis",
        empty="no components",
    )


def _signal_status[SignalT: StrEnum](
    signal: SignalT,
    mapping: dict[SignalT, tuple[str, str]],
) -> tuple[str, str]:
    """Map a signal value to a (status_label, style) pair."""
    return mapping.get(signal, (f"unknown ({signal.value})", "dim"))


def _provider_status(
    prov: "ProviderDiagnosis",
) -> tuple[str, str]:
    """Derive aggregate status for a provider diagnosis."""
    from vaultspec_core.core.diagnosis import (
        ContentSignal,
        ManifestEntrySignal,
        ProviderDirSignal,
    )

    if prov.manifest_entry == ManifestEntrySignal.NOT_INSTALLED:
        return ("skip", "dim")

    error_signals = (
        prov.manifest_entry == ManifestEntrySignal.ORPHANED,
        prov.dir_state == ProviderDirSignal.MISSING,
    )
    if any(error_signals):
        return ("error", "red")

    warn_signals = (
        prov.dir_state in (ProviderDirSignal.PARTIAL, ProviderDirSignal.MIXED),
        prov.manifest_entry == ManifestEntrySignal.UNTRACKED,
        any(s != ContentSignal.CLEAN for s in prov.content.values()),
    )
    if any(warn_signals):
        return ("warn", "yellow")

    return ("ok", "green")


def _gitattributes_weight(signal: "GitattributesSignal") -> tuple[bool, bool]:
    """Return ``(error, warn)`` for the gitattributes row.

    The twin of :func:`_gitignore_weight`. An installed workspace that has not
    declined the block and does not carry one is not having its line endings
    normalised, which is a claim the install makes and this row is the only
    thing that checks.
    """
    from vaultspec_core.core.diagnosis import GitattributesSignal

    return (
        signal == GitattributesSignal.CORRUPTED,
        signal
        in (
            GitattributesSignal.UNMANAGED,
            GitattributesSignal.PARTIAL,
            # A check that did not run cannot vouch for the block either.
            GitattributesSignal.UNREADABLE,
        ),
    )


def _gitignore_weight(signal: "GitignoreSignal") -> tuple[bool, bool]:
    """Return ``(error, warn)`` for the gitignore row.

    An installed workspace with no managed block, or one that has fallen
    behind the recommended set, is not protecting the per-machine artefacts
    the install writes. Both used to print and change nothing, so a gate on
    this command could not tell the reader their workspace was exposed.
    """
    from vaultspec_core.core.diagnosis import GitignoreSignal

    return (
        signal == GitignoreSignal.CORRUPTED,
        signal
        in (
            GitignoreSignal.UNMANAGED,
            GitignoreSignal.PARTIAL,
            # A check that did not run cannot vouch for the block either.
            GitignoreSignal.UNREADABLE,
        ),
    )


def doctor_exit_code(
    diag: "WorkspaceDiagnosis",
) -> int:
    """Compute the doctor exit code from a diagnosis.

    Returns:
        ``0`` if all ok/info, ``1`` if any warnings, ``2`` if any errors.
    """
    from vaultspec_core.core.diagnosis import (
        BuiltinVersionSignal,
        ConfigSignal,
        ContentSignal,
        FrameworkSignal,
        ManifestEntrySignal,
        ModeMismatchSignal,
        PrecommitSignal,
        ProviderDirSignal,
        RenameIntegritySignal,
        VaultContentSignal,
        VersionFloorSignal,
    )

    has_error = False
    has_warn = False

    if diag.framework in (
        FrameworkSignal.MISSING,
        FrameworkSignal.CORRUPTED,
    ):
        has_error = True
    # Adoptable is a coherent workspace awaiting its per-machine manifest, not a
    # broken one: actionable, so a warning, but never an error.
    if diag.framework == FrameworkSignal.ADOPTABLE:
        has_warn = True
    gitignore_error, gitignore_warn = _gitignore_weight(diag.gitignore)
    has_error = has_error or gitignore_error
    has_warn = has_warn or gitignore_warn
    gitattributes_error, gitattributes_warn = _gitattributes_weight(diag.gitattributes)
    has_error = has_error or gitattributes_error
    has_warn = has_warn or gitattributes_warn
    if diag.precommit in (
        PrecommitSignal.INCOMPLETE,
        PrecommitSignal.NON_CANONICAL,
        PrecommitSignal.NO_HOOKS,
        # A perfect config that nothing executes is the failure this whole
        # row exists to report, so it warns exactly as a broken config does.
        PrecommitSignal.NOT_INSTALLED,
        # Content-verified genuine stranding: prek.toml owns the boundary
        # and lacks the canonical hooks, so nothing runs them anywhere.
        PrecommitSignal.UNREFRESHABLE,
        # The collector could not run, so this row vouches for nothing.
        PrecommitSignal.UNREADABLE,
    ):
        has_warn = True
    if diag.builtin_version == BuiltinVersionSignal.DELETED:
        has_error = True
    elif diag.builtin_version == BuiltinVersionSignal.MODIFIED:
        has_warn = True

    if diag.migration_status == "pending":
        has_warn = True
    if diag.vault_content in (
        VaultContentSignal.ANNOTATIONS,
        VaultContentSignal.UNREADABLE,
    ):
        has_warn = True

    # The `mcp` row was rendered and never weighed, so a `.mcp.json` this
    # command could not read still exited 0 while `sync` refused the same
    # workspace (issue #407). Only the could-not-run reading is weighed here:
    # whether the pre-existing MISSING and REGISTRY_DRIFT readings should also
    # gate is a policy question this change deliberately leaves alone.
    if diag.mcp == ConfigSignal.UNREADABLE:
        has_warn = True

    if diag.rename_integrity == RenameIntegritySignal.ERROR:
        has_error = True
    elif diag.rename_integrity == RenameIntegritySignal.MISMATCH:
        has_warn = True

    # A declared-vs-observed install-mode mismatch is a warning; a running
    # version below the committed floor is a hard error on doctor, mirroring the
    # refuse-and-tell that install and sync raise. Weighed per declared package
    # when a packages map exists so a companion package's mismatch or floor
    # violation counts; UNKNOWN and CLEAN are neither. A legacy workspace with no
    # packages map falls back to core's own top-level view.
    if diag.packages:
        for pkg_diag in diag.packages.values():
            if pkg_diag.mode_mismatch == ModeMismatchSignal.MISMATCH:
                has_warn = True
            if pkg_diag.version_floor == VersionFloorSignal.BELOW:
                has_error = True
    else:
        if diag.mode_mismatch == ModeMismatchSignal.MISMATCH:
            has_warn = True
        if diag.version_floor == VersionFloorSignal.BELOW:
            has_error = True

    for prov in diag.providers.values():
        if prov.manifest_entry == ManifestEntrySignal.NOT_INSTALLED:
            continue
        if prov.manifest_entry == ManifestEntrySignal.ORPHANED:
            has_error = True
        elif prov.manifest_entry == ManifestEntrySignal.UNTRACKED:
            has_warn = True
        if prov.dir_state == ProviderDirSignal.MISSING:
            has_error = True
        elif prov.dir_state in (
            ProviderDirSignal.EMPTY,
            ProviderDirSignal.PARTIAL,
        ):
            has_warn = True
        # ProviderDirSignal.MIXED is a soft, informational signal: it means the
        # provider directory carries extra files vaultspec does not own. That is
        # benign (genuine managed-content drift surfaces via ContentSignal), so
        # it must not fail the doctor exit code and block markdown commits via
        # the bundled spec-check hook (issue #122).
        if prov.config in (
            ConfigSignal.MISSING,
            ConfigSignal.FOREIGN,
            ConfigSignal.REGISTRY_DRIFT,
        ):
            has_warn = True
        if any(
            s
            in (
                ContentSignal.STALE,
                ContentSignal.DIVERGED,
                ContentSignal.MISSING,
            )
            for s in prov.content.values()
        ):
            has_warn = True

    if has_error:
        return 2
    if has_warn:
        return 1
    return 0


def _gate(exit_code: int, *, gate_errors: bool) -> int:
    """Fold the warning exit to 0 when *gate_errors* is set.

    The doctor's native contract is 0/1/2 for ok/warnings/errors. The
    pre-commit gate opts into error-only blocking with ``--gate-errors``:
    warning-level provider-mirror lag is the expected steady state after any
    builtins change (``check-provider-artifacts`` forbids committing the
    regenerated mirror), so a warning-strict gate would deadlock every commit.
    Errors (exit 2) still fail; a clean run (0) is unaffected.

    Args:
        exit_code: The native doctor exit code (0, 1, or 2).
        gate_errors: When ``True``, map the warning code (1) to 0.

    Returns:
        The gated exit code.
    """
    if gate_errors and exit_code < 2:
        return 0
    return exit_code
