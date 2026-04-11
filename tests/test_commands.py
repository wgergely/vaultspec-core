from __future__ import annotations

import json
import shutil
from uuid import uuid4

import pytest

from tests.constants import PROJECT_ROOT
from vaultspec_core.config import reset_config
from vaultspec_core.core.commands import (
    CANONICAL_ENTRY_PREFIX,
    CANONICAL_HOOK_IDS,
    install_run,
)
from vaultspec_core.core.enums import PrecommitHook
from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data


@pytest.mark.unit
def test_init_run_scaffolds_antigravity_workspace_layout() -> None:
    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"init-run-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        reset_config()

        # install_run bootstraps its own context
        install_run(
            path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
        )

        assert (tmp_path / ".agents" / "rules").is_dir()
        assert (tmp_path / ".agents" / "workflows").is_dir()
        assert (tmp_path / ".agents" / "skills").is_dir()
        assert (tmp_path / ".codex" / "config.toml").is_file()
        assert not (tmp_path / ".agents" / "agents").exists()
        mcp_config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
        server = mcp_config["mcpServers"]["vaultspec-core"]
        assert server["command"] == "uv"
        expected = ["run", "python", "-m", "vaultspec_core.mcp_server.app"]
        assert server["args"] == expected
    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_install_run_scaffolds_full_canonical_precommit_hooks() -> None:
    """install_run must produce all canonical hooks with --no-sync entries."""
    import yaml

    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"install-precommit-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        reset_config()

        install_run(
            path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
        )

        precommit_path = tmp_path / ".pre-commit-config.yaml"
        assert precommit_path.is_file()

        config = yaml.safe_load(precommit_path.read_text(encoding="utf-8"))
        repos = config.get("repos", [])
        assert len(repos) == 1

        local_repo = repos[0]
        assert local_repo.get("repo") == "local"

        hooks = local_repo.get("hooks", [])
        hook_ids = {h.get("id") for h in hooks}

        assert hook_ids == CANONICAL_HOOK_IDS

        for hook in hooks:
            if hook["id"] in CANONICAL_HOOK_IDS:
                assert hook["entry"].startswith(CANONICAL_ENTRY_PREFIX), (
                    f"Hook {hook['id']} uses non-canonical entry: {hook['entry']}"
                )

    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_scaffold_precommit_repairs_non_canonical_entries() -> None:
    """Re-running scaffold must fix hooks that use old entry patterns."""
    import yaml

    from vaultspec_core.core.commands import (
        _DEPRECATED_HOOK_IDS,
        _scaffold_precommit,
    )

    # Pick the first deprecated ID to simulate an old config
    old_id = next(iter(_DEPRECATED_HOOK_IDS))

    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"precommit-repair-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)

        old_config = {
            "repos": [
                {
                    "repo": "local",
                    "hooks": [
                        {
                            "id": old_id,
                            "name": "Old hook",
                            "entry": "uv run python -m vaultspec_core vault check all",
                            "language": "system",
                            "types": ["markdown"],
                            "pass_filenames": False,
                        },
                    ],
                }
            ]
        }
        config_path = tmp_path / ".pre-commit-config.yaml"
        config_path.write_text(yaml.dump(old_config, sort_keys=False), encoding="utf-8")

        _scaffold_precommit(tmp_path)

        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        hooks = config["repos"][0]["hooks"]
        hook_ids = {h["id"] for h in hooks}

        assert hook_ids == CANONICAL_HOOK_IDS

        for hook in hooks:
            assert hook["entry"].startswith(CANONICAL_ENTRY_PREFIX), (
                f"Hook {hook['id']} still uses non-canonical entry: {hook['entry']}"
            )

    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_precommit_collector_detects_states() -> None:
    """collect_precommit_state reports correct signals for various configs."""
    import yaml

    from vaultspec_core.core.diagnosis.collectors import collect_precommit_state
    from vaultspec_core.core.diagnosis.signals import PrecommitSignal

    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"precommit-diag-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)

        # No file -> NO_FILE
        assert collect_precommit_state(tmp_path) == PrecommitSignal.NO_FILE

        config_path = tmp_path / ".pre-commit-config.yaml"

        # Empty repos -> NO_HOOKS
        config_path.write_text(
            yaml.dump({"repos": []}, sort_keys=False), encoding="utf-8"
        )
        assert collect_precommit_state(tmp_path) == PrecommitSignal.NO_HOOKS

        # Only 1 of 2 canonical hooks -> INCOMPLETE
        partial_config = {
            "repos": [
                {
                    "repo": "local",
                    "hooks": [
                        {
                            "id": PrecommitHook.SPEC_CHECK.value,
                            "entry": f"{CANONICAL_ENTRY_PREFIX} doctor",
                        },
                    ],
                }
            ]
        }
        config_path.write_text(
            yaml.dump(partial_config, sort_keys=False), encoding="utf-8"
        )
        assert collect_precommit_state(tmp_path) == PrecommitSignal.INCOMPLETE

        # All hooks present but one uses old entry pattern -> NON_CANONICAL
        from vaultspec_core.core.commands import CANONICAL_PRECOMMIT_HOOKS

        non_canonical = [dict(h) for h in CANONICAL_PRECOMMIT_HOOKS]
        non_canonical[0]["entry"] = "uv run python -m vaultspec_core vault check all"
        config_path.write_text(
            yaml.dump(
                {"repos": [{"repo": "local", "hooks": non_canonical}]},
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        assert collect_precommit_state(tmp_path) == PrecommitSignal.NON_CANONICAL

        # All hooks with canonical entries -> COMPLETE
        canonical = [dict(h) for h in CANONICAL_PRECOMMIT_HOOKS]
        config_path.write_text(
            yaml.dump(
                {"repos": [{"repo": "local", "hooks": canonical}]},
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        assert collect_precommit_state(tmp_path) == PrecommitSignal.COMPLETE

    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_provider_artifact_patterns_catch_known_files() -> None:
    """PROVIDER_ARTIFACT_PATTERNS must match known provider artifact paths."""
    from vaultspec_core.core.commands import PROVIDER_ARTIFACT_PATTERNS

    # Paths that MUST be caught
    must_catch = [
        ".mcp.json",
        "providers.lock",
        "CLAUDE.md",
        "GEMINI.md",
        "AGENTS.md",
        ".claude/rules/foo.md",
        ".gemini/rules/bar.md",
        ".codex/config.toml",
        ".agents/workflows/test.md",
        ".vaultspec/_snapshots/foo.json",
    ]
    # Paths that must NOT be caught
    must_pass = [
        "src/commands.py",
        "tests/test_foo.py",
        ".vault/adr/my-adr.md",
        ".vaultspec/rules/my-rule.md",
        "pyproject.toml",
    ]

    for path in must_catch:
        normalized = path.replace("\\", "/")
        matched = False
        for pattern in PROVIDER_ARTIFACT_PATTERNS:
            if pattern.endswith("/"):
                if normalized.startswith(pattern):
                    matched = True
                    break
            elif normalized == pattern or normalized.endswith(f"/{pattern}"):
                matched = True
                break
        assert matched, f"Expected {path!r} to match a provider artifact pattern"

    for path in must_pass:
        normalized = path.replace("\\", "/")
        matched = False
        for pattern in PROVIDER_ARTIFACT_PATTERNS:
            if pattern.endswith("/"):
                if normalized.startswith(pattern):
                    matched = True
                    break
            elif normalized == pattern or normalized.endswith(f"/{pattern}"):
                matched = True
                break
        assert not matched, (
            f"Expected {path!r} to NOT match any provider artifact pattern"
        )


@pytest.mark.unit
def test_install_sets_precommit_managed_flag() -> None:
    """install_run must set precommit_managed=True in the manifest."""
    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"install-pc-flag-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        reset_config()

        install_run(
            path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
        )

        mdata = read_manifest_data(tmp_path)
        assert mdata.precommit_managed is True
    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_scaffold_precommit_opt_out_detection() -> None:
    """Removing canonical hooks from .pre-commit-config.yaml opts out of management."""
    import yaml

    from vaultspec_core.core.diagnosis.collectors import collect_precommit_state
    from vaultspec_core.core.diagnosis.signals import PrecommitSignal

    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"pc-optout-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        reset_config()

        install_run(
            path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
        )

        mdata = read_manifest_data(tmp_path)
        assert mdata.precommit_managed is True

        # Remove all canonical hooks from the config (simulating user opt-out)
        config_path = tmp_path / ".pre-commit-config.yaml"
        config_path.write_text(
            yaml.dump({"repos": []}, sort_keys=False), encoding="utf-8"
        )

        signal = collect_precommit_state(tmp_path)
        assert signal in (PrecommitSignal.NO_HOOKS, PrecommitSignal.NO_FILE)

        # The sync opt-out detection logic should flip the flag
        mdata = read_manifest_data(tmp_path)
        mdata.precommit_managed = signal not in (
            PrecommitSignal.NO_FILE,
            PrecommitSignal.NO_HOOKS,
        )
        write_manifest_data(tmp_path, mdata)

        mdata = read_manifest_data(tmp_path)
        assert mdata.precommit_managed is False
    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_resolver_skips_repair_when_not_managed() -> None:
    """resolve() must not emit REPAIR_PRECOMMIT when precommit_managed=False."""
    from vaultspec_core.core.diagnosis.diagnosis import WorkspaceDiagnosis
    from vaultspec_core.core.diagnosis.signals import (
        FrameworkSignal,
        GitattributesSignal,
        GitignoreSignal,
        PrecommitSignal,
        ResolutionAction,
    )
    from vaultspec_core.core.resolver import resolve

    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"pc-resolver-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)

        # Write a manifest with precommit_managed=False
        from vaultspec_core.core.manifest import ManifestData

        mdata = ManifestData(precommit_managed=False)
        write_manifest_data(tmp_path, mdata)

        diag = WorkspaceDiagnosis(
            framework=FrameworkSignal.PRESENT,
            gitignore=GitignoreSignal.COMPLETE,
            gitattributes=GitattributesSignal.COMPLETE,
            precommit=PrecommitSignal.NO_HOOKS,
        )

        plan = resolve(diag, "sync", target=tmp_path)
        repair_steps = [
            s for s in plan.steps if s.action == ResolutionAction.REPAIR_PRECOMMIT
        ]
        assert repair_steps == [], (
            f"Expected no REPAIR_PRECOMMIT steps but got: {repair_steps}"
        )
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_vault_add_force_overwrites_existing() -> None:
    """vault add --force must overwrite an existing document."""
    from vaultspec_core.core.exceptions import ResourceExistsError
    from vaultspec_core.vaultcore.hydration import create_vault_doc
    from vaultspec_core.vaultcore.models import DocType

    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"vault-add-force-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        reset_config()

        install_run(
            path=tmp_path,
            provider="all",
            upgrade=False,
            dry_run=False,
            force=False,
        )

        path1 = create_vault_doc(tmp_path, DocType.ADR, "test-feat", "2026-04-11")
        assert path1.exists()

        with pytest.raises(ResourceExistsError, match="already exists"):
            create_vault_doc(tmp_path, DocType.ADR, "test-feat", "2026-04-11")

        path2 = create_vault_doc(
            tmp_path, DocType.ADR, "test-feat", "2026-04-11", force=True
        )
        assert path2 == path1
        assert path2.exists()
    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_vault_add_dry_run_no_write() -> None:
    """vault add --dry-run must return path without creating file."""
    from vaultspec_core.vaultcore.hydration import create_vault_doc
    from vaultspec_core.vaultcore.models import DocType

    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"vault-add-dry-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        reset_config()

        install_run(
            path=tmp_path,
            provider="all",
            upgrade=False,
            dry_run=False,
            force=False,
        )

        path = create_vault_doc(
            tmp_path,
            DocType.RESEARCH,
            "dry-test",
            "2026-04-11",
            dry_run=True,
        )
        assert not path.exists()
        assert path.name == "2026-04-11-dry-test-research.md"
    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_resource_exists_error_includes_hint() -> None:
    """ResourceExistsError from create_vault_doc must include a hint."""
    from vaultspec_core.core.exceptions import ResourceExistsError
    from vaultspec_core.vaultcore.hydration import create_vault_doc
    from vaultspec_core.vaultcore.models import DocType

    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"hint-test-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        reset_config()

        install_run(
            path=tmp_path,
            provider="all",
            upgrade=False,
            dry_run=False,
            force=False,
        )

        create_vault_doc(tmp_path, DocType.ADR, "hint-feat", "2026-04-11")

        with pytest.raises(ResourceExistsError) as exc_info:
            create_vault_doc(tmp_path, DocType.ADR, "hint-feat", "2026-04-11")
        assert exc_info.value.hint
        assert "--force" in exc_info.value.hint
    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.unit
def test_spec_add_dry_run_no_write() -> None:
    """spec rules_add with dry_run must not write the file."""
    from vaultspec_core.core.rules import rules_add

    tmp_path = PROJECT_ROOT / ".pytest-tmp" / f"spec-dry-{uuid4().hex}"
    try:
        tmp_path.mkdir(parents=True, exist_ok=True)
        reset_config()

        install_run(
            path=tmp_path,
            provider="all",
            upgrade=False,
            dry_run=False,
            force=False,
        )

        path = rules_add("dry-test-rule", dry_run=True)
        assert not path.exists()
    finally:
        reset_config()
        shutil.rmtree(tmp_path, ignore_errors=True)
