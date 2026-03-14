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
        "sync",
        "lock",
        "fix",
        "check",
        "test",
        "build",
        "publish",
    }
    missing = [name for name in sorted(required) if not _recipe_exists(justfile, name)]
    assert not missing, f"Missing required just recipes: {missing}"


def test_justfile_exposes_approved_targets() -> None:
    justfile = _read("justfile")
    assert "sync target='dependencies':" in justfile
    assert "lock target='dependencies':" in justfile
    assert "fix target='lint':" in justfile
    assert "check target='all':" in justfile
    assert "test target='all':" in justfile
    assert "build target:" in justfile
    assert "publish target tag:" in justfile
    for target in ("dependencies", "dependency-upgrades"):
        assert target in justfile
    for target in (
        "lint",
        "type",
        "dependencies",
        "links",
        "toml",
        "markdown",
        "workflow",
        "vault",
        "all",
    ):
        assert target in justfile
    for target in ("python", "docker", "all"):
        assert target in justfile
    assert "docker-ghcr" in justfile


def test_dependency_audit_uses_lockfile_export_without_root_project() -> None:
    justfile = _read("justfile")
    export_cmd = 'uv export --frozen --group dev --no-emit-project --output-file "$tmp"'
    audit_cmd = 'uv run pip-audit --strict -r "$tmp"'
    assert export_cmd in justfile
    assert audit_cmd in justfile


def test_check_all_runs_every_validation_surface() -> None:
    justfile = _read("justfile")
    assert "just check lint" in justfile
    assert "just check type" in justfile
    assert "just check dependencies" in justfile
    assert "just check links" in justfile
    assert "just check toml" in justfile
    assert "just check markdown" in justfile
    assert "just check workflow" in justfile
    assert "just check vault" in justfile
    assert "just test all" in justfile


def test_test_all_runs_python_and_docker() -> None:
    justfile = _read("justfile")
    assert "just test python" in justfile
    assert "just test docker" in justfile
    assert "just build docker" in justfile
    assert "just build python" in justfile


def test_fix_surface_includes_lint_markdown_and_vault() -> None:
    justfile = _read("justfile")
    assert "fix target='lint':" in justfile
    assert "uv run ruff format src tests" in justfile
    assert "uv run ruff check --fix src tests" in justfile
    assert "npx --yes @taplo/cli fmt *.toml" in justfile
    mdlint_fix = (
        "npx --yes markdownlint-cli"
        " --config .markdownlint.json --fix .vaultspec/ .vault/ README.md"
    )
    assert mdlint_fix in justfile
    assert "uv run python -m vaultspec_core vault audit --verify --fix" in justfile


def test_markdown_check_and_fix_use_markdownlint() -> None:
    justfile = _read("justfile")
    mdlint_check = (
        "npx --yes markdownlint-cli"
        " --config .markdownlint.json .vaultspec/ .vault/ README.md"
    )
    assert mdlint_check in justfile


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


def test_dockerfile_defaults_to_vaultspec_core_help() -> None:
    dockerfile = _read("Dockerfile")
    assert 'CMD ["vaultspec-core", "--help"]' in dockerfile
