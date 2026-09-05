"""Tests for diagnosis signal enums and dataclasses."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.diagnosis.diagnosis import (
    ProviderDiagnosis,
    WorkspaceDiagnosis,
)
from vaultspec_core.core.diagnosis.signals import (
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
    ResolutionAction,
    VaultContentSignal,
    VersionFloorSignal,
)
from vaultspec_core.core.enums import CliAction, PrecommitHook, Tool

if TYPE_CHECKING:
    from enum import Enum
    from pathlib import Path

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("enum_cls", "expected_members"),
    [
        (
            FrameworkSignal,
            {"MISSING", "CORRUPTED", "ADOPTABLE", "PRESENT"},
        ),
        (
            ProviderDirSignal,
            {"MISSING", "EMPTY", "PARTIAL", "COMPLETE", "MIXED"},
        ),
        (
            ManifestEntrySignal,
            {"COHERENT", "ORPHANED", "UNTRACKED", "NOT_INSTALLED"},
        ),
        (
            ContentSignal,
            {"CLEAN", "DIVERGED", "STALE", "MISSING"},
        ),
        (
            BuiltinVersionSignal,
            {"CURRENT", "MODIFIED", "DELETED", "NO_SNAPSHOTS"},
        ),
        (
            ConfigSignal,
            {
                "OK",
                "MISSING",
                "FOREIGN",
                "PARTIAL_MCP",
                "USER_MCP",
                "REGISTRY_DRIFT",
                "UNREADABLE",
            },
        ),
        (
            GitignoreSignal,
            {
                "NO_FILE",
                "NO_ENTRIES",
                "UNMANAGED",
                "UNREADABLE",
                "PARTIAL",
                "COMPLETE",
                "CORRUPTED",
            },
        ),
        (
            GitattributesSignal,
            {
                "NO_FILE",
                "NO_ENTRIES",
                "UNMANAGED",
                "UNREADABLE",
                "PARTIAL",
                "COMPLETE",
                "CORRUPTED",
            },
        ),
        (
            PrecommitSignal,
            {
                "NO_FILE",
                "NO_HOOKS",
                "INCOMPLETE",
                "NON_CANONICAL",
                "UNREFRESHABLE",
                "ORPHANED",
                "NOT_INSTALLED",
                "UNREADABLE",
                "COMPLETE",
            },
        ),
        (
            VaultContentSignal,
            {
                "NO_VAULT",
                "CLEAN",
                "ANNOTATIONS",
                "UNREADABLE",
            },
        ),
        (
            RenameIntegritySignal,
            {
                "CLEAN",
                "MISMATCH",
                "ERROR",
            },
        ),
        (
            PrecommitHook,
            {
                "VAULT_FIX",
                "VAULT_SANITIZE_ANNOTATIONS",
                "CHECK_PROVIDER_ARTIFACTS",
                "SPEC_CHECK",
            },
        ),
        (
            CliAction,
            {
                "INSTALL",
                "UPGRADE",
                "SYNC",
                "UNINSTALL",
                "DOCTOR",
            },
        ),
        (
            ResolutionAction,
            {
                "SCAFFOLD",
                "SYNC",
                "PRUNE",
                "REPAIR_MANIFEST",
                "ADOPT_DIRECTORY",
                "ADOPT_FRAMEWORK",
                "REPAIR_GITIGNORE",
                "REPAIR_GITATTRIBUTES",
                "REPAIR_PRECOMMIT",
                "REMOVE",
                "SKIP",
            },
        ),
    ],
)
def test_enum_members(enum_cls: type[Enum], expected_members: set[str]) -> None:
    assert set(enum_cls.__members__) == expected_members


@pytest.mark.parametrize(
    ("enum_cls", "member", "value"),
    [
        (ResolutionAction, "SCAFFOLD", "scaffold"),
        (ResolutionAction, "SKIP", "skip"),
        (FrameworkSignal, "PRESENT", "present"),
        (GitignoreSignal, "NO_FILE", "no_file"),
        (RenameIntegritySignal, "CLEAN", "clean"),
    ],
)
def test_enum_string_values(enum_cls: type[Enum], member: str, value: str) -> None:
    assert enum_cls[member] == value
    assert enum_cls[member].value == value


class TestProviderDiagnosis:
    def test_construction_minimal(self):
        diag = ProviderDiagnosis(
            tool=Tool.CLAUDE,
            dir_state=ProviderDirSignal.COMPLETE,
            manifest_entry=ManifestEntrySignal.COHERENT,
        )
        assert diag.tool == Tool.CLAUDE
        assert diag.dir_state == ProviderDirSignal.COMPLETE
        assert diag.manifest_entry == ManifestEntrySignal.COHERENT
        assert diag.content == {}
        assert diag.config == ConfigSignal.OK

    def test_construction_full(self):
        content = {"rules.md": ContentSignal.DIVERGED}
        diag = ProviderDiagnosis(
            tool=Tool.GEMINI,
            dir_state=ProviderDirSignal.PARTIAL,
            manifest_entry=ManifestEntrySignal.ORPHANED,
            content=content,
            config=ConfigSignal.OK,
        )
        assert diag.content == content
        assert diag.config == ConfigSignal.OK


class TestWorkspaceDiagnosis:
    def test_construction_minimal(self):
        diag = WorkspaceDiagnosis(framework=FrameworkSignal.PRESENT)
        assert diag.framework == FrameworkSignal.PRESENT
        assert diag.providers == {}
        assert diag.builtin_version == BuiltinVersionSignal.NO_SNAPSHOTS
        assert diag.gitignore == GitignoreSignal.NO_FILE
        assert diag.gitattributes == GitattributesSignal.NO_FILE
        assert diag.vault_content == VaultContentSignal.NO_VAULT
        assert diag.vault_annotation_count == 0
        assert diag.vault_unreadable_count == 0
        assert diag.rename_integrity == RenameIntegritySignal.CLEAN
        assert diag.rename_mismatch_count == 0

    def test_construction_with_providers(self):
        prov = ProviderDiagnosis(
            tool=Tool.CLAUDE,
            dir_state=ProviderDirSignal.COMPLETE,
            manifest_entry=ManifestEntrySignal.COHERENT,
        )
        diag = WorkspaceDiagnosis(
            framework=FrameworkSignal.PRESENT,
            providers={Tool.CLAUDE: prov},
            builtin_version=BuiltinVersionSignal.CURRENT,
            gitignore=GitignoreSignal.COMPLETE,
        )
        assert Tool.CLAUDE in diag.providers
        assert diag.builtin_version == BuiltinVersionSignal.CURRENT
        assert diag.gitignore == GitignoreSignal.COMPLETE


class TestDoctorExitCode:
    """The doctor exit code must not block commits on soft signals (issue #122)."""

    def _clean_workspace(self, prov: ProviderDiagnosis) -> WorkspaceDiagnosis:
        return WorkspaceDiagnosis(
            framework=FrameworkSignal.PRESENT,
            providers={prov.tool: prov},
            builtin_version=BuiltinVersionSignal.CURRENT,
            gitignore=GitignoreSignal.COMPLETE,
            gitattributes=GitattributesSignal.COMPLETE,
            precommit=PrecommitSignal.COMPLETE,
            migration_status="up_to_date",
            vault_content=VaultContentSignal.CLEAN,
            rename_integrity=RenameIntegritySignal.CLEAN,
        )

    def test_mixed_provider_dir_does_not_fail_exit_code(self) -> None:
        """A MIXED provider directory is informational and must exit 0.

        A real Claude Code / Codex workspace always carries host-native files;
        before the fix, MIXED set has_warn and the doctor exited 1, which the
        bundled spec-check pre-commit hook turned into a blocked markdown commit.
        """
        from vaultspec_core.cli.spec_cmd import doctor_exit_code

        prov = ProviderDiagnosis(
            tool=Tool.CLAUDE,
            dir_state=ProviderDirSignal.MIXED,
            manifest_entry=ManifestEntrySignal.COHERENT,
        )
        assert doctor_exit_code(self._clean_workspace(prov)) == 0

    def test_partial_provider_dir_still_warns(self) -> None:
        """PARTIAL remains a genuine warning - the fix is scoped to MIXED."""
        from vaultspec_core.cli.spec_cmd import doctor_exit_code

        prov = ProviderDiagnosis(
            tool=Tool.CLAUDE,
            dir_state=ProviderDirSignal.PARTIAL,
            manifest_entry=ManifestEntrySignal.COHERENT,
        )
        assert doctor_exit_code(self._clean_workspace(prov)) == 1


class TestDoctorModeAndFloorWeighting:
    """Doctor weights the install-mode and floor signals correctly."""

    def _prov(self) -> ProviderDiagnosis:
        return ProviderDiagnosis(
            tool=Tool.CLAUDE,
            dir_state=ProviderDirSignal.COMPLETE,
            manifest_entry=ManifestEntrySignal.COHERENT,
        )

    def _workspace(
        self,
        *,
        mode_mismatch: ModeMismatchSignal = ModeMismatchSignal.CLEAN,
        version_floor: VersionFloorSignal = VersionFloorSignal.OK,
    ) -> WorkspaceDiagnosis:
        return WorkspaceDiagnosis(
            framework=FrameworkSignal.PRESENT,
            providers={Tool.CLAUDE: self._prov()},
            builtin_version=BuiltinVersionSignal.CURRENT,
            gitignore=GitignoreSignal.COMPLETE,
            gitattributes=GitattributesSignal.COMPLETE,
            precommit=PrecommitSignal.COMPLETE,
            migration_status="up_to_date",
            vault_content=VaultContentSignal.CLEAN,
            rename_integrity=RenameIntegritySignal.CLEAN,
            mode_mismatch=mode_mismatch,
            version_floor=version_floor,
        )

    def test_clean_mode_and_no_floor_exit_zero(self) -> None:
        from vaultspec_core.cli.spec_cmd import doctor_exit_code

        assert doctor_exit_code(self._workspace()) == 0

    def test_unknown_mode_is_not_a_warning(self) -> None:
        from vaultspec_core.cli.spec_cmd import doctor_exit_code

        diag = self._workspace(mode_mismatch=ModeMismatchSignal.UNKNOWN)
        assert doctor_exit_code(diag) == 0

    def test_mode_mismatch_warns(self) -> None:
        from vaultspec_core.cli.spec_cmd import doctor_exit_code

        diag = self._workspace(mode_mismatch=ModeMismatchSignal.MISMATCH)
        assert doctor_exit_code(diag) == 1

    def test_below_floor_is_an_error(self) -> None:
        from vaultspec_core.cli.spec_cmd import doctor_exit_code

        diag = self._workspace(version_floor=VersionFloorSignal.BELOW)
        assert doctor_exit_code(diag) == 2

    def test_below_floor_outranks_mode_warning(self) -> None:
        from vaultspec_core.cli.spec_cmd import doctor_exit_code

        diag = self._workspace(
            mode_mismatch=ModeMismatchSignal.MISMATCH,
            version_floor=VersionFloorSignal.BELOW,
        )
        assert doctor_exit_code(diag) == 2


class TestCollectorFailureIsNotHealth:
    """A check that could not run must not report the benign value (issue #407).

    Every `_safe_*` wrapper caught a collector failure and returned the neutral
    signal for its row, so "could not be read" was indistinguishable from
    "simply absent" and `doctor` exited 0 on a workspace every mutating verb
    refused.
    """

    @staticmethod
    def _break_the_precommit_collector(root: Path) -> None:
        """Corrupt `workspace.json`, which the precommit collector reads."""
        (root / ".vaultspec" / "workspace.json").write_text(
            '{"packages": {', encoding="utf-8"
        )

    def test_precommit_reports_unreadable_not_absent(self, tmp_path: Path) -> None:
        from vaultspec_core.core.diagnosis.diagnosis import _safe_precommit_state
        from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

        WorkspaceFactory(tmp_path).install("claude")
        self._break_the_precommit_collector(tmp_path)

        assert _safe_precommit_state(tmp_path) is PrecommitSignal.UNREADABLE

    def test_doctor_weighs_unreadable_as_a_warning(self, tmp_path: Path) -> None:
        """The row is not enough; the exit code has to move too."""
        from vaultspec_core.cli.spec_cmd_doctor import doctor_exit_code
        from vaultspec_core.core.diagnosis.diagnosis import WorkspaceDiagnosis
        from vaultspec_core.core.diagnosis.signals import FrameworkSignal

        clean = WorkspaceDiagnosis(framework=FrameworkSignal.PRESENT)
        assert doctor_exit_code(clean) == 0

        for degraded in (
            WorkspaceDiagnosis(
                framework=FrameworkSignal.PRESENT,
                precommit=PrecommitSignal.UNREADABLE,
            ),
            WorkspaceDiagnosis(
                framework=FrameworkSignal.PRESENT,
                gitignore=GitignoreSignal.UNREADABLE,
            ),
            WorkspaceDiagnosis(
                framework=FrameworkSignal.PRESENT,
                gitattributes=GitattributesSignal.UNREADABLE,
            ),
        ):
            assert doctor_exit_code(degraded) == 1

    def test_unreadable_never_triggers_a_repair(self, tmp_path: Path) -> None:
        """Unobserved is not a licence to rewrite the file.

        The guard on the change: a signal that means "nobody looked" must not
        reach a resolution step, or preflight would repair on a guess.
        """
        from vaultspec_core.core.resolver import ResolutionPlan
        from vaultspec_core.core.resolver_repo import (
            resolve_gitattributes,
            resolve_gitignore,
            resolve_precommit,
        )

        plan = ResolutionPlan()
        resolve_gitignore(
            plan, GitignoreSignal.UNREADABLE, CliAction.INSTALL, force=True
        )
        resolve_gitattributes(
            plan, GitattributesSignal.UNREADABLE, CliAction.INSTALL, force=True
        )
        resolve_precommit(
            plan, PrecommitSignal.UNREADABLE, CliAction.INSTALL, force=True
        )

        assert plan.steps == []


class TestUndecodableFilesAreReportedNotCrashedOn:
    """#407's two remaining halves.

    `UnicodeDecodeError` subclasses `ValueError`, not `OSError`, so it sat
    outside every `(YAMLError, OSError)` net: an undecodable managed file made
    `sync` and `install --force` die with a raw traceback.

    Widening those nets has a trap, which these tests pin. Once a collector
    stops raising, it also stops reaching the `_safe_*` handler that reports
    UNREADABLE - so the row silently reverts to the benign reading unless the
    collector reports the distinction itself.
    """

    @staticmethod
    def _write_undecodable(path: Path) -> None:
        path.write_bytes(b"\xff\xfe\x00garbage\n")

    def test_undecodable_precommit_reads_unreadable_not_absent(
        self, tmp_path: Path
    ) -> None:
        from vaultspec_core.core.diagnosis.collectors import collect_precommit_state
        from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

        WorkspaceFactory(tmp_path).install("claude")
        self._write_undecodable(tmp_path / ".pre-commit-config.yaml")

        assert collect_precommit_state(tmp_path) is PrecommitSignal.UNREADABLE

    def test_an_absent_precommit_config_stays_benign(self, tmp_path: Path) -> None:
        """The guard: only a file that exists and cannot be read is degraded."""
        from vaultspec_core.core.diagnosis.collectors import collect_precommit_state
        from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

        WorkspaceFactory(tmp_path).install("claude")
        (tmp_path / ".pre-commit-config.yaml").unlink()

        assert collect_precommit_state(tmp_path) is PrecommitSignal.NO_FILE

    def test_corrupt_mcp_config_reads_unreadable(self, tmp_path: Path) -> None:
        from vaultspec_core.core.diagnosis.collectors import collect_mcp_config_state
        from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

        WorkspaceFactory(tmp_path).install("claude")
        (tmp_path / ".mcp.json").write_text('{"mcpServers": {', encoding="utf-8")

        assert collect_mcp_config_state(tmp_path) is ConfigSignal.UNREADABLE

    def test_a_parseable_mcp_config_without_servers_stays_benign(
        self, tmp_path: Path
    ) -> None:
        """The guard on the probe.

        `read_mcp_servers` answers None for four different things. Only the
        ones that mean "could not read" may degrade; a file that parsed fine
        and simply carries no `mcpServers` mapping is ordinary.
        """
        from vaultspec_core.core.diagnosis.collectors import collect_mcp_config_state
        from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

        WorkspaceFactory(tmp_path).install("claude")
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")

        assert collect_mcp_config_state(tmp_path) is ConfigSignal.PARTIAL_MCP

    def test_doctor_weighs_an_unreadable_mcp_row(self, tmp_path: Path) -> None:
        """The `mcp` row was rendered and never weighed."""
        from vaultspec_core.cli.spec_cmd_doctor import doctor_exit_code
        from vaultspec_core.core.diagnosis.diagnosis import WorkspaceDiagnosis
        from vaultspec_core.core.diagnosis.signals import FrameworkSignal

        degraded = WorkspaceDiagnosis(
            framework=FrameworkSignal.PRESENT, mcp=ConfigSignal.UNREADABLE
        )

        assert doctor_exit_code(degraded) == 1
