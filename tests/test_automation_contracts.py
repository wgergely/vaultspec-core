from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _load_yaml(path: str) -> dict:
    return yaml.safe_load(_read(path))


def _recipe_exists(justfile_text: str, name: str) -> bool:
    pattern = rf"(?m)^{re.escape(name)}(?:\s|:)"
    return re.search(pattern, justfile_text) is not None


def test_justfile_contains_required_recipes() -> None:
    justfile = _read("justfile")
    required = {
        "prod",
        "dev",
        "ci",
        "_dev-deps",
        "_dev-lint",
        "_dev-format",
        "_dev-audit",
        "_dev-test",
        "_dev-build",
        "_dev-publish",
        "_dev-precommit",
    }
    missing = [name for name in sorted(required) if not _recipe_exists(justfile, name)]
    assert not missing, f"Missing required just recipes: {missing}"


def test_justfile_exposes_approved_targets() -> None:
    justfile = _read("justfile")
    # Top-level namespace recipes
    assert "prod *args='':" in justfile
    assert "dev target *args='':" in justfile
    assert "ci:" in justfile
    # Internal dev recipes with default targets
    assert "_dev-deps target='sync':" in justfile
    assert "_dev-lint target='all':" in justfile
    assert "_dev-format target='all':" in justfile
    assert "_dev-audit target:" in justfile
    assert "_dev-test target='all':" in justfile
    assert "_dev-build target:" in justfile
    assert "_dev-publish target tag:" in justfile
    assert "_dev-precommit target='run':" in justfile
    # Dev dispatch covers all verbs
    for verb in (
        "deps",
        "lint",
        "format",
        "audit",
        "test",
        "build",
        "publish",
        "precommit",
    ):
        assert verb in justfile
    # Lint sub-targets
    for target in ("python", "type", "links", "toml", "markdown", "workflow"):
        assert target in justfile
    # Build/test sub-targets
    for target in ("python", "docker", "all"):
        assert target in justfile
    assert "docker-ghcr" in justfile


def test_dependency_audit_uses_lockfile_export_without_root_project() -> None:
    justfile = _read("justfile")
    # Export and audit commands are split across continuation lines
    assert "uv export --frozen --group dev" in justfile
    assert "--no-emit-project --output-file" in justfile
    assert 'uv run pip-audit --strict -r "$tmp"' in justfile


def test_lint_all_runs_every_validation_surface() -> None:
    justfile = _read("justfile")
    assert "just _dev-lint python" in justfile
    assert "just _dev-lint type" in justfile
    assert "just _dev-lint links" in justfile
    assert "just _dev-lint toml" in justfile
    assert "just _dev-lint markdown" in justfile
    assert "just _dev-lint workflow" in justfile


def test_test_all_runs_python_and_docker() -> None:
    justfile = _read("justfile")
    assert "just _dev-test python" in justfile
    assert "just _dev-test docker" in justfile
    assert "just _dev-build docker" in justfile
    assert "just _dev-build python" in justfile


def test_format_surface_includes_python_toml_and_markdown() -> None:
    justfile = _read("justfile")
    assert "_dev-format target='all':" in justfile
    assert "uv run ruff format src tests" in justfile
    assert "uv run ruff check --fix src tests" in justfile
    assert '@taplo/cli fmt "$(pwd)"/*.toml' in justfile
    assert "markdownlint-cli" in justfile
    assert "--config .markdownlint.json --fix" in justfile


def test_markdown_lint_uses_markdownlint() -> None:
    justfile = _read("justfile")
    assert "npx --yes markdownlint-cli" in justfile
    assert "--config .markdownlint.json" in justfile
    assert ".vaultspec/ .vault/ README.md" in justfile


def test_ci_workflow_calls_just_for_quality_gates() -> None:
    ci = _load_yaml(".github/workflows/ci.yml")
    jobs = ci["jobs"]
    required_jobs = {
        "workflow-lint",
        "lint-and-type",
        "tests",
        "vault-audit",
        "dependency-audit",
    }
    assert required_jobs.issubset(jobs), "CI workflow is missing required jobs"

    expected_runs = {
        "lint-and-type": {
            "just sync dependencies",
            "just check lint",
            "just check type",
            "just check toml",
            "just check links",
            "just check markdown",
        },
        "tests": {"just sync dependencies", "just test python"},
        "vault-audit": {"just sync dependencies", "just check vault"},
        "dependency-audit": {"just sync dependencies", "just check dependencies"},
    }

    for job_name, expected in expected_runs.items():
        steps = jobs[job_name]["steps"]
        run_commands = {step.get("run") for step in steps if "run" in step}
        missing = [cmd for cmd in sorted(expected) if cmd not in run_commands]
        assert not missing, f"Job {job_name} missing just commands: {missing}"


def test_ci_workflow_uses_actionlint() -> None:
    ci = _load_yaml(".github/workflows/ci.yml")
    jobs = ci["jobs"]
    steps = jobs["workflow-lint"]["steps"]
    used_actions = {step.get("uses") for step in steps if "uses" in step}
    assert "docker://rhysd/actionlint:latest" in used_actions


def test_ci_workflow_installs_node_and_lychee_for_config_and_link_checks() -> None:
    ci = _load_yaml(".github/workflows/ci.yml")
    jobs = ci["jobs"]
    steps = jobs["lint-and-type"]["steps"]
    used_actions = {step.get("uses") for step in steps if "uses" in step}
    assert "actions/setup-node@v4" in used_actions
    assert "taiki-e/install-action@v2" in used_actions


def test_docker_workflow_builds_and_smokes_on_pr() -> None:
    docker = _load_yaml(".github/workflows/docker.yml")
    jobs = docker["jobs"]
    assert "docker-build" in jobs, "Docker workflow missing PR build job"
    steps = jobs["docker-build"]["steps"]
    run_commands = [step.get("run") for step in steps if "run" in step]
    assert "just test docker" in run_commands


def test_docker_publish_workflow_uses_standard_registry_actions() -> None:
    docker = _load_yaml(".github/workflows/docker.yml")
    jobs = docker["jobs"]
    assert "docker-publish" in jobs, "Docker workflow missing publish job"
    steps = jobs["docker-publish"]["steps"]
    used_actions = {step.get("uses") for step in steps if "uses" in step}
    required = {
        "docker/setup-buildx-action@v3",
        "docker/metadata-action@v5",
        "docker/login-action@v3",
        "docker/build-push-action@v6",
        "actions/attest-build-provenance@v2",
    }
    missing = [action for action in sorted(required) if action not in used_actions]
    assert not missing, f"Docker publish workflow missing required actions: {missing}"


def test_prod_delegates_to_cli() -> None:
    justfile = _read("justfile")
    # prod recipe passes all args through to uv run vaultspec-core
    assert "prod *args='':" in justfile
    assert "uv run vaultspec-core {{args}}" in justfile
    # install/uninstall available via prod namespace (documented in comments)
    assert "just prod install" in justfile
    assert "uv run vaultspec-core" in justfile


def test_provider_capability_enum_covers_all_tools() -> None:
    """Every Tool enum member must have a ToolConfig with non-empty capabilities."""
    from vaultspec_core.core.enums import Tool
    from vaultspec_core.core.types import init_paths

    init_paths(ROOT)
    from vaultspec_core.core import types as _t

    for tool in Tool:
        cfg = _t.TOOL_CONFIGS.get(tool)
        assert cfg is not None, f"Tool {tool.value} has no ToolConfig"
        assert cfg.capabilities, f"Tool {tool.value} has empty capabilities"


def test_provider_capability_consistency() -> None:
    """Capability declarations must be consistent with ToolConfig fields."""
    from vaultspec_core.core.enums import ProviderCapability, Tool
    from vaultspec_core.core.types import init_paths

    init_paths(ROOT)
    from vaultspec_core.core import types as _t

    for tool in Tool:
        cfg = _t.TOOL_CONFIGS.get(tool)
        if cfg is None:
            continue
        caps = cfg.capabilities
        if ProviderCapability.RULES in caps:
            assert cfg.rules_dir is not None or cfg.native_config_file is not None, (
                f"{tool.value} declares RULES but has no rules_dir"
                " or native_config_file"
            )
        if ProviderCapability.SKILLS in caps:
            assert cfg.skills_dir is not None, (
                f"{tool.value} declares SKILLS but has no skills_dir"
            )
        if ProviderCapability.ROOT_CONFIG in caps:
            assert cfg.config_file is not None, (
                f"{tool.value} declares ROOT_CONFIG but has no config_file"
            )


def test_every_capability_has_at_least_one_provider() -> None:
    """Each ProviderCapability value must map to at least one provider."""
    from vaultspec_core.core.enums import ProviderCapability, Tool
    from vaultspec_core.core.types import init_paths

    init_paths(ROOT)
    from vaultspec_core.core import types as _t

    for cap in ProviderCapability:
        providers = [
            tool.value
            for tool in Tool
            if cap
            in _t.TOOL_CONFIGS.get(
                tool, type("", (), {"capabilities": frozenset()})()
            ).capabilities
        ]
        assert providers, f"ProviderCapability.{cap.name} has no providers"


def test_dockerfile_defaults_to_vaultspec_core_help() -> None:
    dockerfile = _read("Dockerfile")
    assert 'CMD ["vaultspec-core", "--help"]' in dockerfile
