from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app
from vaultspec_core.config import reset_config
from vaultspec_core.core.commands import (
    CANONICAL_ENTRY_PREFIX,
    CANONICAL_HOOK_IDS,
    entry_prefix_for_mode,
    install_run,
    sync_provider,
)
from vaultspec_core.core.enums import InstallMode, PrecommitHook
from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data


@pytest.mark.unit
def test_init_run_scaffolds_antigravity_workspace_layout(tmp_path: Path) -> None:
    try:
        reset_config()

        # install_run bootstraps its own context
        install_run(
            path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
        )

        assert (tmp_path / ".agents" / "rules").is_dir()
        assert (tmp_path / ".agents" / "workflows").is_dir()
        assert (tmp_path / ".agents" / "skills").is_dir()
        assert (tmp_path / ".codex" / "config.toml").is_file()
        # Antigravity discovers workspace subagents at `.agents/agents/`.
        assert (tmp_path / ".agents" / "agents").is_dir()
        mcp_config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
        server = mcp_config["mcpServers"]["vaultspec-core"]
        assert server["command"] == "uvx"
        expected = [
            "--from",
            "vaultspec-core",
            "python",
            "-m",
            "vaultspec_core.mcp_server.app",
        ]
        assert server["args"] == expected
    finally:
        reset_config()


@pytest.mark.unit
def test_install_run_scaffolds_full_canonical_precommit_hooks(tmp_path: Path) -> None:
    """install_run must produce all canonical hooks with --no-sync entries."""
    import yaml

    try:
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
                assert hook["entry"].startswith(
                    entry_prefix_for_mode(InstallMode.TOOL)
                ), f"Hook {hook['id']} uses non-canonical entry: {hook['entry']}"

    finally:
        reset_config()


@pytest.mark.unit
def test_scaffold_precommit_repairs_non_canonical_entries(tmp_path: Path) -> None:
    """Re-running scaffold must fix hooks that use old entry patterns."""
    import yaml

    from vaultspec_core.core.commands import (
        scaffold_precommit,
    )

    # Pick the first canonical ID to simulate an old config
    old_id = next(iter(CANONICAL_HOOK_IDS))

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

    scaffold_precommit(tmp_path)

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    hooks = config["repos"][0]["hooks"]
    hook_ids = {h["id"] for h in hooks}

    assert hook_ids == CANONICAL_HOOK_IDS

    for hook in hooks:
        assert hook["entry"].startswith(CANONICAL_ENTRY_PREFIX), (
            f"Hook {hook['id']} still uses non-canonical entry: {hook['entry']}"
        )


@pytest.mark.unit
def test_precommit_collector_detects_states(tmp_path: Path) -> None:
    """collect_precommit_state reports correct signals for various configs."""
    import yaml

    from vaultspec_core.core.diagnosis.collectors import collect_precommit_state
    from vaultspec_core.core.diagnosis.signals import PrecommitSignal

    # No file -> NO_FILE
    assert collect_precommit_state(tmp_path) == PrecommitSignal.NO_FILE

    config_path = tmp_path / ".pre-commit-config.yaml"

    # Empty repos -> NO_HOOKS
    config_path.write_text(yaml.dump({"repos": []}, sort_keys=False), encoding="utf-8")
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
    config_path.write_text(yaml.dump(partial_config, sort_keys=False), encoding="utf-8")
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
        ".vaultspec/my-rule.md",
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
def test_install_sets_precommit_managed_flag(tmp_path: Path) -> None:
    """install_run must set precommit_managed=True in the manifest."""
    try:
        reset_config()

        install_run(
            path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
        )

        mdata = read_manifest_data(tmp_path)
        assert mdata.precommit_managed is True
    finally:
        reset_config()


@pytest.mark.unit
def test_scaffold_precommit_opt_out_detection(tmp_path: Path) -> None:
    """Removing canonical hooks from .pre-commit-config.yaml opts out of management."""
    import yaml

    from vaultspec_core.core.diagnosis.collectors import collect_precommit_state
    from vaultspec_core.core.diagnosis.signals import PrecommitSignal

    try:
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


@pytest.mark.unit
def test_resolver_skips_repair_when_not_managed(tmp_path: Path) -> None:
    """resolve() must not emit REPAIR_PRECOMMIT when precommit_managed=False."""
    from vaultspec_core.core.diagnosis.diagnosis import WorkspaceDiagnosis
    from vaultspec_core.core.diagnosis.signals import (
        FrameworkSignal,
        GitattributesSignal,
        GitignoreSignal,
        PrecommitSignal,
        ResolutionAction,
    )

    # Write a manifest with precommit_managed=False
    from vaultspec_core.core.manifest import ManifestData
    from vaultspec_core.core.resolver import resolve

    mdata = ManifestData(precommit_managed=False)
    write_manifest_data(tmp_path, mdata)

    diag = WorkspaceDiagnosis(
        framework=FrameworkSignal.PRESENT,
        gitignore=GitignoreSignal.COMPLETE,
        gitattributes=GitattributesSignal.COMPLETE,
        precommit=PrecommitSignal.NO_HOOKS,
    )

    from vaultspec_core.core.enums import CliAction

    plan = resolve(diag, CliAction.SYNC, target=tmp_path)
    repair_steps = [
        s for s in plan.steps if s.action == ResolutionAction.REPAIR_PRECOMMIT
    ]
    assert repair_steps == [], (
        f"Expected no REPAIR_PRECOMMIT steps but got: {repair_steps}"
    )


@pytest.mark.unit
def test_vault_add_force_overwrites_existing(tmp_path: Path) -> None:
    """vault add --force must overwrite an existing document."""
    from vaultspec_core.core.exceptions import ResourceExistsError
    from vaultspec_core.vaultcore.hydration import (
        DocumentIdentity,
        WritePolicy,
        create_vault_doc,
    )
    from vaultspec_core.vaultcore.models import DocType

    try:
        reset_config()

        install_run(
            path=tmp_path,
            provider="all",
            upgrade=False,
            dry_run=False,
            force=False,
        )

        identity = DocumentIdentity(DocType.ADR, "test-feat", "2026-04-11")
        path1 = create_vault_doc(tmp_path, identity)
        assert path1.exists()

        with pytest.raises(ResourceExistsError, match="already exists"):
            create_vault_doc(tmp_path, identity)

        path2 = create_vault_doc(tmp_path, identity, write=WritePolicy(force=True))
        assert path2 == path1
        assert path2.exists()
    finally:
        reset_config()


@pytest.mark.unit
def test_vault_add_dry_run_no_write(tmp_path: Path) -> None:
    """vault add --dry-run must return path without creating file."""
    from vaultspec_core.vaultcore.hydration import (
        DocumentIdentity,
        WritePolicy,
        create_vault_doc,
    )
    from vaultspec_core.vaultcore.models import DocType

    try:
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
            DocumentIdentity(DocType.RESEARCH, "dry-test", "2026-04-11"),
            write=WritePolicy(dry_run=True),
        )
        assert not path.exists()
        assert path.name == "2026-04-11-dry-test-research.md"
    finally:
        reset_config()


@pytest.mark.unit
def test_vault_add_creates_distinct_same_day_topic_infixed_adrs(tmp_path: Path) -> None:
    """The public CLI creates distinct ADR records for distinct topic infixes."""
    try:
        reset_config()
        install_run(
            path=tmp_path,
            provider="all",
            upgrade=False,
            dry_run=False,
            force=False,
        )

        runner = CliRunner(env={"NO_COLOR": "1"})
        first = runner.invoke(
            app,
            [
                "vault",
                "add",
                "adr",
                "--feature",
                "same-day-decisions",
                "--topic",
                "circuit-accounting",
                "--date",
                "2026-07-27",
                "--target",
                str(tmp_path),
            ],
        )
        second = runner.invoke(
            app,
            [
                "vault",
                "add",
                "adr",
                "--feature",
                "same-day-decisions",
                "--topic",
                "sibling-adoption",
                "--date",
                "2026-07-27",
                "--target",
                str(tmp_path),
            ],
        )
        duplicate = runner.invoke(
            app,
            [
                "vault",
                "add",
                "adr",
                "--feature",
                "same-day-decisions",
                "--topic",
                "circuit-accounting",
                "--date",
                "2026-07-27",
                "--target",
                str(tmp_path),
            ],
        )

        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output
        assert duplicate.exit_code == 1, duplicate.output
        adr_dir = tmp_path / ".vault" / "adr"
        assert (
            adr_dir / "2026-07-27-same-day-decisions-circuit-accounting-adr.md"
        ).is_file()
        assert (
            adr_dir / "2026-07-27-same-day-decisions-sibling-adoption-adr.md"
        ).is_file()
        assert "already exists" in duplicate.output
    finally:
        reset_config()


@pytest.mark.unit
def test_resource_exists_error_includes_hint(tmp_path: Path) -> None:
    """ResourceExistsError from create_vault_doc must include a hint."""
    from vaultspec_core.core.exceptions import ResourceExistsError
    from vaultspec_core.vaultcore.hydration import DocumentIdentity, create_vault_doc
    from vaultspec_core.vaultcore.models import DocType

    try:
        reset_config()

        install_run(
            path=tmp_path,
            provider="all",
            upgrade=False,
            dry_run=False,
            force=False,
        )

        identity = DocumentIdentity(DocType.ADR, "hint-feat", "2026-04-11")
        create_vault_doc(tmp_path, identity)

        with pytest.raises(ResourceExistsError) as exc_info:
            create_vault_doc(tmp_path, identity)
        assert exc_info.value.hint
        assert "--force" in exc_info.value.hint
    finally:
        reset_config()


@pytest.mark.unit
def test_spec_add_dry_run_no_write(tmp_path: Path) -> None:
    """spec rules_add with dry_run must not write the file."""
    from vaultspec_core.core.rules import rules_add

    try:
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


@pytest.mark.unit
def test_sync_all_result_count_matches_resource_labels(tmp_path: Path) -> None:
    """sync_provider('all') results render without a label/result mismatch.

    Regression test for #54 (the CLI display once zipped resource_labels with
    sync results) extended for #133: sync now appends a trailing structural-
    backfill result after the positional resource passes, so the renderer must
    tolerate one result beyond the labels rather than crash. Assert the exact
    contract (one result per resource label plus the backfill) and that the
    real outcome-collector consumes the results without raising.
    """
    from vaultspec_core.cli.root import collect_sync_outcomes

    try:
        reset_config()

        install_run(
            path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
        )

        results = sync_provider("all")

        resource_labels = [
            "rules",
            "skills",
            "agents",
            "system",
            "config",
            "mcps",
            "hooks",
        ]
        # One result per resource label, plus the trailing structural backfill.
        assert len(results) == len(resource_labels) + 1, (
            f"sync_provider('all') returned {len(results)} results; expected "
            f"{len(resource_labels)} resource passes plus one structural backfill"
        )

        # The collector must consume the variable-length results without the
        # historical strict-zip ValueError.
        outcomes = collect_sync_outcomes(results, "all", [])
        assert isinstance(outcomes, list)
    finally:
        reset_config()
