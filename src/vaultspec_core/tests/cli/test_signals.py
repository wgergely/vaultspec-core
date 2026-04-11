"""Tests for diagnosis signal enums and dataclasses."""

from __future__ import annotations

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
    PrecommitSignal,
    ProviderDirSignal,
    ResolutionAction,
)
from vaultspec_core.core.enums import PrecommitHook, Tool

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("enum_cls", "expected_members"),
    [
        (
            FrameworkSignal,
            {"MISSING", "CORRUPTED", "PRESENT"},
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
            {"OK", "MISSING", "FOREIGN", "PARTIAL_MCP", "USER_MCP", "REGISTRY_DRIFT"},
        ),
        (
            GitignoreSignal,
            {"NO_FILE", "NO_ENTRIES", "PARTIAL", "COMPLETE", "CORRUPTED"},
        ),
        (
            GitattributesSignal,
            {"NO_FILE", "NO_ENTRIES", "PARTIAL", "COMPLETE", "CORRUPTED"},
        ),
        (
            PrecommitSignal,
            {
                "NO_FILE",
                "NO_HOOKS",
                "INCOMPLETE",
                "NON_CANONICAL",
                "COMPLETE",
            },
        ),
        (
            PrecommitHook,
            {
                "VAULT_FIX",
                "CHECK_PROVIDER_ARTIFACTS",
                "SPEC_CHECK",
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
                "REPAIR_GITIGNORE",
                "REPAIR_GITATTRIBUTES",
                "REPAIR_PRECOMMIT",
                "REMOVE",
                "SKIP",
            },
        ),
    ],
)
def test_enum_members(enum_cls, expected_members):
    assert set(enum_cls.__members__) == expected_members


@pytest.mark.parametrize(
    ("enum_cls", "member", "value"),
    [
        (ResolutionAction, "SCAFFOLD", "scaffold"),
        (ResolutionAction, "SKIP", "skip"),
        (FrameworkSignal, "PRESENT", "present"),
        (GitignoreSignal, "NO_FILE", "no_file"),
    ],
)
def test_enum_string_values(enum_cls, member, value):
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
        assert diag.config == ConfigSignal.MISSING

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
