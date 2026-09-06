"""Contracts binding the repository's automation surfaces to each other.

The failures guarded here are the ones no single tool reports: a CI job that
stops invoking the gate it claims to run, a ``justfile`` recipe that grows
shell logic the declarative registry was meant to own, a threshold that drifts
away from its declaration site, or two independent type-check invocations that
quietly stop covering the same trees.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import TypedDict, cast, get_args

import pytest
import yaml

pytestmark = [pytest.mark.repo]

#: Repository root (``dev/guards/`` -> ``dev/`` -> repo).
ROOT = Path(__file__).resolve().parents[2]

#: A sentinel step condition of the form ``outputs.state == 'healthy'``.
_SENTINEL_STATE_CONDITION = re.compile(
    r"steps\.judge\.outputs\.state\s*[=!]=\s*'(?P<state>[a-z-]+)'"
)


class _PreCommitHook(TypedDict):
    """One hook entry under a ``.pre-commit-config.yaml`` repo block."""

    id: str
    entry: str


class _PreCommitRepo(TypedDict):
    """One repo block in ``.pre-commit-config.yaml``."""

    hooks: list[_PreCommitHook]


class _PreCommitConfig(TypedDict):
    """The top-level shape of ``.pre-commit-config.yaml``."""

    repos: list[_PreCommitRepo]


#: One step in a GitHub Actions job. Declared functionally because `if` is a
#: Python keyword and so cannot be an attribute in the class syntax.
_WorkflowStep = TypedDict(
    "_WorkflowStep",
    {"name": str, "run": str, "uses": str, "if": str},
    total=False,
)


class _WorkflowJob(TypedDict):
    """One job in a GitHub Actions workflow."""

    steps: list[_WorkflowStep]


class _Workflow(TypedDict):
    """The top-level shape of a GitHub Actions workflow file."""

    jobs: dict[str, _WorkflowJob]


class _BasedpyrightExecutionEnvironment(TypedDict, total=False):
    """One override block under ``[[tool.basedpyright.executionEnvironments]]``."""

    root: str
    reportPrivateUsage: bool


class _BasedpyrightConfig(TypedDict):
    """The slice of ``[tool.basedpyright]`` this guard reads."""

    include: list[str]
    executionEnvironments: list[_BasedpyrightExecutionEnvironment]


class _PyprojectToolTable(TypedDict):
    """The ``[tool]`` table, narrowed to what this guard reads."""

    basedpyright: _BasedpyrightConfig


class _PyprojectConfig(TypedDict):
    """The top-level shape of ``pyproject.toml``, narrowed to what this guard reads."""

    tool: _PyprojectToolTable


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _load_yaml(path: str) -> object:
    return yaml.safe_load(_read(path))


def _load_pre_commit_config() -> _PreCommitConfig:
    """Parse ``.pre-commit-config.yaml`` into its known schema.

    Invariant: this repo's own config always nests
    ``repos: [{hooks: [{id: ...}]}]``; ``yaml.safe_load`` has no schema of
    its own, so this cast is the one place that shape is asserted.
    """
    return cast("_PreCommitConfig", _load_yaml(".pre-commit-config.yaml"))


def _load_workflow(path: str) -> _Workflow:
    """Parse a GitHub Actions workflow file into its known schema.

    Invariant: this repo's own workflow files always nest
    ``jobs: {name: {steps: [{run?, uses?, ...}]}}``; ``yaml.safe_load`` has
    no schema of its own, so this cast is the one place that shape is
    asserted.
    """
    return cast("_Workflow", _load_yaml(path))


def _load_basedpyright_config() -> _BasedpyrightConfig:
    """Parse ``[tool.basedpyright]`` out of ``pyproject.toml``.

    Invariant: this repo's own ``pyproject.toml`` always declares the table
    with an ``executionEnvironments`` array of tables; ``tomllib`` has no
    schema of its own, so this cast is the one place that shape is asserted.
    """
    raw = tomllib.loads(_read("pyproject.toml"))
    # Routed through `object` because a plain dict and a TypedDict are never
    # considered sufficiently overlapping for a direct cast, regardless of how
    # well the shape is known; the intermediate step expresses that, rather
    # than signalling an unproven shape.
    parsed = cast("_PyprojectConfig", cast("object", raw))
    return parsed["tool"]["basedpyright"]


def _colocated_test_dirs() -> set[str]:
    """Return every co-located ``tests/`` directory basedpyright checks.

    The trees are read from basedpyright's own ``include`` list rather than
    hardcoded, so this follows the configuration when the layout moves. That
    is not hypothetical: the co-location convention started inside
    ``src/vaultspec_core`` alone and now spans the instrument trees too, and a
    guard naming one tree by hand would have gone quietly half-blind at the
    moment the others appeared.
    """
    included = _load_basedpyright_config()["include"]
    found = {
        path.relative_to(ROOT).as_posix()
        for tree in included
        for path in (ROOT / tree).rglob("tests")
        if path.is_dir() and "__pycache__" not in path.parts
    }
    # The caller subtracts this set from the exemption list and asserts the
    # remainder is empty, so an empty set here passes unconditionally - a
    # renamed tree under `include` would retire the guard rather than trip it.
    assert found, f"no co-located tests directories found under {included}"
    return found


def _recipe_exists(justfile_text: str, name: str) -> bool:
    pattern = rf"(?m)^{re.escape(name)}(?:\s|:)"
    return re.search(pattern, justfile_text) is not None


def test_justfile_exposes_every_verb_at_the_root() -> None:
    """Every entry point is a root verb; there is no nested dispatch namespace.

    The harness was previously reached through `just dev <verb>` with a
    parallel `just prod` mirror of the shipped CLI.  Both are gone: the
    justfile is a development-only file, so a `dev` namespace inside it named
    nothing, and mirroring a finished product's CLI only adds a layer that
    drifts.  This pins the collapse so neither reappears.
    """
    justfile = _read("justfile")
    missing = [
        name
        for name in sorted(
            {
                "deps",
                "lint",
                "fix",
                "audit",
                "test",
                "build",
                "vault",
                "framework",
                "docs",
                "health",
                "ci",
            }
        )
        if not _recipe_exists(justfile, name)
    ]
    assert not missing, f"Missing required just recipes: {missing}"

    assert not _recipe_exists(justfile, "prod"), (
        "`just prod` mirrored the shipped vaultspec-core CLI and was removed; "
        "invoke the product directly with `uv run --no-sync vaultspec-core`."
    )
    assert not re.search(r"(?m)^_dev-", justfile), (
        "The `_dev-*` internal recipe namespace was collapsed to root verbs."
    )


def test_justfile_delegates_every_verb_to_the_dev_package() -> None:
    """No recipe may carry shell logic; `dev/toolchain.py` is the only source.

    The justfile previously branched on `os()` and embedded PowerShell
    `switch` bodies, which meant every target existed twice and could drift
    between platforms.  Each recipe is now a single delegation, so the
    declarative toolchain is the one place a target is defined.
    """
    justfile = _read("justfile")
    for verb in ("deps", "lint", "fix", "audit", "test", "build", "health"):
        assert re.search(
            rf"(?m)^{verb} target='[a-z-]+':\n\s+\{{\{{dev\}}\}} {verb} ", justfile
        ), f"Recipe `{verb}` must delegate to the dev package in one line"
    for shell_ism in ('if os() == "windows"', "switch (", "Get-Command", "elseif"):
        assert shell_ism not in justfile, (
            f"Shell branching {shell_ism!r} belongs in dev/toolchain.py, "
            "not the justfile"
        )


def test_dependency_audit_uses_uv_native_scanner() -> None:
    # The invocation moved out of the justfile into the declarative toolchain
    # when every recipe collapsed to a single delegation; the contract is
    # unchanged, so it is asserted against its new home.
    toolchain = _read("dev/toolchain.py")
    audit_script = _read("dev/audit/dependency_audit.py")
    # The supply-chain gate's justfile recipe delegates to the cross-platform
    # audit wrapper, which runs uv's native auditor against the frozen
    # lockfile. The default scope already covers the project plus the default
    # dependency groups, so no group-selection flag is pinned: --all-groups
    # was accepted by uv 0.10.x but rejected by 0.11.x, and breaking CI on a
    # uv minor bump is exactly the brittleness this audit is meant to prevent.
    assert "dev/audit/dependency_audit.py" in toolchain
    assert "uv audit" in audit_script
    assert "--preview-features" in audit_script
    assert "--frozen" in audit_script
    # This is a uv-managed project: the supply-chain gate is uv-native end to
    # end and never shells out to pip. pip-audit drags `pip` itself into the
    # environment as a transitive dependency - historically the only
    # vulnerability `uv audit` ever reported here - so no pip-named scanner
    # may appear in the recipe or the wrapper. When uv's preview decoder
    # aborts on a malformed OSV record, the wrapper independently repeats the
    # bulk OSV query rather than falling back to a second tool.
    for surface in (toolchain, audit_script):
        assert "pip-audit" not in surface
        assert "pip-tools" not in surface


def test_pyproject_has_no_pip_named_dev_tools() -> None:
    pyproject = _read("pyproject.toml")
    # uv-managed projects do not need pip-named tooling. pip-audit drags in
    # `pip` itself as a transitive dependency, which historically introduced
    # the only vulnerability `uv audit` reported on this project.  The
    # contract: no pip-named dev tool may appear in either dev surface
    # (the optional-dependencies dev extra or the dependency-groups dev
    # group); use `uv audit` and uv-native commands instead.
    assert "pip-audit" not in pyproject
    assert "pip-tools" not in pyproject
    assert '"pip"' not in pyproject  # bare pip pin
    assert "pipenv" not in pyproject


def test_changelog_is_release_please_managed() -> None:
    """CHANGELOG.md must be the un-edited release-please artifact.

    Manual edits to CHANGELOG.md drift away from the lockstep
    commit-history -> changelog mapping that release-please maintains and
    silently break the next release PR.  Hand-written headers from older
    Keep-a-Changelog templates (`### Added`, `### Changed`, `### Removed`,
    `### Deprecated`, `### Security`, `[Unreleased]`) are the canonical
    fingerprint of manual content; their absence proves that
    release-please is the only writer.

    The pre-commit hook ``block-manual-changelog`` blocks fresh
    hand-edits at commit time; this test catches drift that lands by
    other means (rebase, force-push, tooling regression).
    """
    changelog = _read("CHANGELOG.md")

    forbidden_keep_a_changelog = (
        "### Added",
        "### Changed",
        "### Removed",
        "### Deprecated",
        "### Security",
        "## [Unreleased]",
        "## Unreleased",
    )
    leaked = [marker for marker in forbidden_keep_a_changelog if marker in changelog]
    assert not leaked, (
        f"CHANGELOG.md contains manual Keep-a-Changelog markers {leaked}; "
        "release-please does not emit those headings.  Remove them and "
        "let release-please regenerate the file."
    )

    # Every release entry must follow the release-please header shape:
    # `## [vX.Y.Z](compare-link) (yyyy-mm-dd)`.  A bare `## X.Y.Z` (no
    # compare link, no date) is a hand-written entry.
    release_headers = re.findall(r"(?m)^## .+$", changelog)
    bad = [h for h in release_headers if not re.match(r"^## \[\d", h)]
    assert not bad, (
        f"CHANGELOG.md has non-release-please section headers: {bad}.  "
        "Every release header must be `## [vX.Y.Z](compare) (date)` as "
        "emitted by release-please-action."
    )


def test_pre_commit_blocks_manual_changelog_edits() -> None:
    """The pre-commit gate against manual CHANGELOG.md edits must be wired.

    Without this hook nothing prevents a developer from staging a
    handwritten changelog entry alongside a code change; the gate is
    what makes "release-please owns CHANGELOG.md" actually enforceable
    on the local commit path.
    """
    config = _load_pre_commit_config()
    hook_ids = {
        hook.get("id")
        for repo in config.get("repos", [])
        for hook in repo.get("hooks", [])
    }
    assert "block-manual-changelog" in hook_ids, (
        "Missing pre-commit hook `block-manual-changelog`; CHANGELOG.md "
        "must be writable only by release-please-action in CI."
    )

    raw = _read(".pre-commit-config.yaml")
    # The hook only fires for CHANGELOG.md (release-please artifact).
    assert "^CHANGELOG\\.md$" in raw


def test_pre_commit_runs_vault_annotation_sanitizer() -> None:
    config = _load_pre_commit_config()
    hooks = [hook for repo in config.get("repos", []) for hook in repo.get("hooks", [])]
    hook_ids = {hook.get("id") for hook in hooks}
    assert "vault-sanitize-annotations" in hook_ids
    ordered_ids = [hook.get("id") for hook in hooks]
    assert ordered_ids.index("vault-fix") < ordered_ids.index(
        "vault-sanitize-annotations"
    )
    assert ordered_ids.index("vault-sanitize-annotations") < ordered_ids.index(
        "spec-check"
    )

    raw = _read(".pre-commit-config.yaml")
    assert "vault sanitize annotations" in raw


def _toolchain_targets(verb_name: str) -> set[str]:
    """Return the target names the dev toolchain declares for one verb."""
    from dev import toolchain

    verb = toolchain.find_verb(verb_name)
    assert verb is not None, f"dev/toolchain.py declares no `{verb_name}` verb"
    return {target.name for target in verb.targets}


def test_lint_covers_every_validation_surface() -> None:
    """The gating dimensions must all be reachable by name."""
    required = {
        "python",
        "type",
        "toml",
        "links",
        "markdown",
        "workflow",
        "complexity",
        "nesting",
        "size",
        "type-strict",
        "all",
    }
    missing = sorted(required - _toolchain_targets("lint"))
    assert not missing, f"lint verb is missing targets: {missing}"


def test_audit_covers_every_advisory_dimension() -> None:
    """Advisory dimensions are named individually so each can graduate to lint."""
    required = {"deps", "security", "dead-code", "dependencies", "complexity", "all"}
    missing = sorted(required - _toolchain_targets("audit"))
    assert not missing, f"audit verb is missing targets: {missing}"


def test_only_the_dependency_audit_gates() -> None:
    """`deps` is a verdict and gates; every other audit dimension is a lead.

    A check whose documented contract and actual exit code disagree is worse
    than no check, so the advisory flag is asserted rather than assumed.
    """
    from dev import toolchain

    audit = toolchain.find_verb("audit")
    assert audit is not None
    by_name = {target.name: target for target in audit.targets}
    assert not by_name["deps"].advisory, "the dependency audit must gate"
    for name in ("security", "dead-code", "dependencies", "complexity"):
        assert by_name[name].advisory, f"audit target `{name}` must be advisory"


def test_health_report_is_measurement_only() -> None:
    """Every health target exits 0; it ranks offenders rather than gating."""
    from dev import toolchain

    health = toolchain.find_verb("health")
    assert health is not None
    assert {"report", "fast", "census"} <= {t.name for t in health.targets}
    for target in health.targets:
        assert target.advisory, (
            f"health target `{target.name}` must be advisory - the report is the "
            "measurement instrument, and the gates live in pyproject.toml"
        )


def test_fix_surface_covers_every_autofixable_target() -> None:
    required = {"python", "toml", "markdown", "vault", "all"}
    missing = sorted(required - _toolchain_targets("fix"))
    assert not missing, f"fix verb is missing targets: {missing}"


def test_bandit_excludes_every_nested_test_tree() -> None:
    """The security scan must not measure test code at any nesting depth.

    A path-shaped exclusion (`<pkg>/tests`) only covers the top-level test
    package and silently admitted `<pkg>/hooks/tests/` and its siblings, which
    is where the scan's only MEDIUM findings came from. The glob covers every
    depth.
    """
    from dev import toolchain
    from dev.runner import Cmd, ToolOrDocker

    audit = toolchain.find_verb("audit")
    assert audit is not None
    security = next(t for t in audit.targets if t.name == "security")
    step = security.steps[0]
    assert isinstance(step, (Cmd, ToolOrDocker))
    argv = step.argv
    assert "-x" in argv, "the bandit scan must carry an exclusion"
    assert argv[argv.index("-x") + 1] == "*/tests/*", (
        "the bandit exclusion must be a glob covering nested test trees"
    )


def _ty_pre_commit_paths() -> set[str]:
    """Return the path arguments the pre-commit ``ty`` hook checks.

    The hook's ``entry`` is a literal shell-style command line rather than
    structured data, so the paths are recovered by locating the ``check``
    token and taking every following word that is not a flag.
    """
    config = _load_pre_commit_config()
    hooks = [hook for repo in config.get("repos", []) for hook in repo.get("hooks", [])]
    ty_hook = next(hook for hook in hooks if hook.get("id") == "ty")
    tokens = ty_hook["entry"].split()
    check_index = tokens.index("check")
    return {token for token in tokens[check_index + 1 :] if not token.startswith("-")}


def _ty_toolchain_paths() -> set[str]:
    """Return the path arguments :mod:`dev.toolchain`'s ``type`` target checks.

    Mirrors :func:`_ty_pre_commit_paths` so both sides are derived from their
    real source rather than a literal expected list, per
    :func:`test_ty_pre_commit_scope_matches_dev_toolchain_scope`.
    """
    from dev import toolchain
    from dev.runner import Cmd

    lint = toolchain.find_verb("lint")
    assert lint is not None
    target = next(t for t in lint.targets if t.name == "type")
    step = target.steps[0]
    assert isinstance(step, Cmd)
    argv = step.argv
    check_index = argv.index("check")
    return {token for token in argv[check_index + 1 :] if not token.startswith("-")}


def test_ty_pre_commit_scope_matches_dev_toolchain_scope() -> None:
    """The pre-commit ``ty`` hook and ``just lint type`` must check the same trees.

    ``.pre-commit-config.yaml``'s ``ty`` hook hardcodes its own argv instead of
    delegating to :mod:`dev.toolchain`, so it is a second, independent source
    of truth for what "type checked" means. If one is widened without the
    other, pre-commit silently checks less than CI while both read as green.
    Both sides are derived from their real source here rather than compared
    against a literal path list, so this fails the moment either one drifts,
    in either direction, without needing an edit of its own when the covered
    trees change.
    """
    pre_commit_paths = _ty_pre_commit_paths()
    toolchain_paths = _ty_toolchain_paths()
    assert pre_commit_paths == toolchain_paths, (
        f"pre-commit `ty` hook checks {sorted(pre_commit_paths)} but "
        f"dev/toolchain.py's `type` target checks {sorted(toolchain_paths)} - "
        "widen both together."
    )


def test_ci_workflow_calls_just_for_quality_gates() -> None:
    ci = _load_workflow(".github/workflows/ci.yml")
    jobs = ci["jobs"]
    required_jobs = {
        "workflow-lint",
        "lint-and-type",
        "tests",
        "windows-vault-repair",
        "vault-audit",
        "dependency-audit",
    }
    assert required_jobs.issubset(jobs), "CI workflow is missing required jobs"

    expected_runs = {
        # The four dimensions below `markdown` are pinned for the same reason
        # the test lanes are: each graduated from advisory to gating only once
        # its burndown reached zero, and an ungated promotion is one deletion
        # away from being silently undone. `type-strict` in particular was
        # promoted by removing its `continue-on-error` key; nothing but this
        # list stops the step itself from being removed next.
        "lint-and-type": {
            "just deps sync",
            "just lint python",
            "just lint type",
            "just lint type-platforms",
            "just lint toml",
            "just lint links",
            "just lint markdown",
            "just lint complexity",
            "just lint nesting",
            "just lint size",
            "just lint type-strict",
        },
        # `harness` and `repo` are pinned alongside `unit` because the lesson
        # that produced them was a lane no CI job named: the guards it ran went
        # unobserved and one of them had been failing undetected. Naming all
        # three here means removing a CI step fails this guard rather than
        # silently shrinking what "green" covers.
        "tests": {
            "just deps sync",
            "just test unit",
            "just test harness",
            "just test repo",
        },
        "windows-vault-repair": {"just deps sync", "just test vault-repair"},
        "vault-audit": {
            "just deps sync",
            "just framework install",
            "just vault check",
        },
        "dependency-audit": {"just deps sync", "just audit deps"},
    }

    for job_name, expected in expected_runs.items():
        steps = jobs[job_name]["steps"]
        run_commands = {step["run"] for step in steps if "run" in step}
        missing = [cmd for cmd in sorted(expected) if cmd not in run_commands]
        assert not missing, f"Job {job_name} missing just commands: {missing}"


def test_ci_workflow_uses_actionlint() -> None:
    ci = _load_workflow(".github/workflows/ci.yml")
    jobs = ci["jobs"]
    steps = jobs["workflow-lint"]["steps"]
    used_actions = {step["uses"] for step in steps if "uses" in step}
    assert any(a.startswith("docker://rhysd/actionlint:") for a in used_actions)


def test_ci_workflow_installs_native_lint_tools() -> None:
    ci = _load_workflow(".github/workflows/ci.yml")
    jobs = ci["jobs"]
    steps = jobs["lint-and-type"]["steps"]
    used_actions = {step["uses"] for step in steps if "uses" in step}
    assert "taiki-e/install-action@v2" in used_actions
    # Node.js is no longer required - taplo and pymarkdown are native
    assert "actions/setup-node@v4" not in used_actions


def test_quality_gate_thresholds_are_declared_not_reimplemented() -> None:
    """Every ratcheted threshold lives in pyproject.toml, not in the harness.

    The harness composes the gates by invoking their tools; the moment it
    carries a threshold of its own, the reported number and the enforced
    number can drift apart. This pins each baseline-calibrated dimension to
    its declaration site.
    """
    pyproject = _read("pyproject.toml")
    for table in (
        "[tool.complexipy]",
        "[tool.pylint.format]",
        "[tool.pylint.design]",
        "[tool.ruff.lint.mccabe]",
        "[tool.ruff.lint.pylint]",
        "[tool.vulture]",
        "[tool.bandit]",
        "[tool.deptry]",
        "[tool.basedpyright]",
    ):
        assert table in pyproject, f"missing gate declaration {table}"

    toolchain = _read("dev/toolchain.py")
    for threshold_flag in (
        "--max-complexity-allowed",
        "--max-module-lines",
        "--max-attributes",
        "--min-confidence",
    ):
        assert threshold_flag not in toolchain, (
            f"{threshold_flag} must be declared in pyproject.toml, not passed "
            "on the command line where it can drift from the gate"
        )


def test_test_tree_exclusion_patterns_match_windows_paths() -> None:
    """Ignore patterns must be TOML literal strings, not basic strings.

    As a basic string, `".*[\\\\/]tests[\\\\/].*"` decodes to the regex
    `.*[\\/]tests[\\/].*`, whose character class contains only a forward slash
    - the backslash reads as an escape of `/` rather than a class member. The
    pattern then never matches a Windows path and the test tree silently
    enters the gate it was meant to leave. Both sibling repositories carry
    this defect; the literal-string form is the fix.
    """
    pyproject = _read("pyproject.toml")
    assert "ignore-paths = ['.*[\\\\/]tests[\\\\/].*']" in pyproject
    assert "extend_exclude = ['.*[\\\\/]tests[\\\\/].*']" in pyproject
    assert '".*[\\\\/]tests[\\\\/].*"' not in pyproject, (
        "a basic-string ignore pattern never matches a Windows path"
    )


def _pytest_addopts() -> str:
    """Return ``[tool.pytest.ini_options].addopts`` from ``pyproject.toml``."""
    raw = tomllib.loads(_read("pyproject.toml"))
    return cast("str", raw["tool"]["pytest"]["ini_options"]["addopts"])


def test_pytest_addopts_deselects_every_credential_or_network_marker() -> None:
    """A bare ``pytest`` invocation must gate the same markers `just test` does.

    `dev.toolchain.EXCLUDED_MARKERS` is what every `just test` lane passes
    explicitly via `-m`, so those invocations never depend on `addopts` at
    all - a later `-m` on the command line simply replaces an earlier one
    from `addopts`, it does not combine with it. A bare `pytest` invocation
    (a contributor's shell, an editor's test runner, CI calling the binary
    directly) has no such explicit `-m` and falls through to `addopts`
    alone, so `addopts` is the ONLY gate for that path. Letting it drift
    from `EXCLUDED_MARKERS` is exactly how `@pytest.mark.gemini` stopped
    being an opt-in gate: the marker was registered and documented as
    excluding the test, while nothing in `addopts` actually deselected it.
    """
    from dev import toolchain

    addopts = _pytest_addopts()
    assert f"not benchmark and {toolchain.EXCLUDED_MARKERS}" in addopts, (
        f"pyproject.toml addopts {addopts!r} has drifted from "
        f"dev.toolchain.EXCLUDED_MARKERS {toolchain.EXCLUDED_MARKERS!r}; a "
        "bare `pytest` invocation would stop deselecting a credential- or "
        "network-gated marker"
    )


def test_provider_capability_enum_covers_all_tools(tmp_path: Path) -> None:
    """Every Tool enum member must have a ToolConfig with non-empty capabilities."""
    from vaultspec_core.core.enums import Tool
    from vaultspec_core.core.types import init_paths

    (tmp_path / ".vaultspec").mkdir()
    ctx = init_paths(tmp_path)

    for tool in Tool:
        cfg = ctx.tool_configs.get(tool)
        assert cfg is not None, f"Tool {tool.value} has no ToolConfig"
        assert cfg.capabilities, f"Tool {tool.value} has empty capabilities"


def test_provider_capability_consistency(tmp_path: Path) -> None:
    """Capability declarations must be consistent with ToolConfig fields."""
    from vaultspec_core.core.enums import ProviderCapability, Tool
    from vaultspec_core.core.types import init_paths

    (tmp_path / ".vaultspec").mkdir()
    ctx = init_paths(tmp_path)

    for tool in Tool:
        cfg = ctx.tool_configs.get(tool)
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
        if ProviderCapability.WORKFLOWS in caps:
            assert cfg.workflows_dir is not None, (
                f"{tool.value} declares WORKFLOWS but has no workflows_dir"
            )


def test_every_capability_has_at_least_one_provider(tmp_path: Path) -> None:
    """Each ProviderCapability value must map to at least one provider."""
    from vaultspec_core.core.enums import ProviderCapability, Tool
    from vaultspec_core.core.types import init_paths

    (tmp_path / ".vaultspec").mkdir()
    ctx = init_paths(tmp_path)

    for cap in ProviderCapability:
        providers = [
            tool.value
            for tool in Tool
            if (cfg := ctx.tool_configs.get(tool)) is not None
            and cap in cfg.capabilities
        ]
        assert providers, f"ProviderCapability.{cap.name} has no providers"


def test_basedpyright_private_usage_exemption_covers_every_tests_directory() -> None:
    """Every co-located ``tests/`` tree needs its own privacy-exemption entry.

    ``executionEnvironments[].root`` matches by directory PREFIX only, so this
    list cannot be collapsed. A glob root such as ``src/vaultspec_core/**/tests``
    is accepted, matches nothing, and reports no error - a silent no-op that
    looks identical to success. A per-directory ``pyrightconfig.json`` is never
    discovered either, because one config is resolved per invocation. A
    file-header ``# pyright: reportPrivateUsage=false`` does work, but needs one
    per file and scatters suppressions through tracked test source, which is
    what this project's ban on inline ``# pyright: ignore`` exists to prevent.

    Each tree therefore needs a literal entry. Without this guard, a new
    co-located suite would instead fail the GATE with a ``reportPrivateUsage``
    error, inviting the one fix the exemption's own comment warns against -
    making the internals public. This makes the omission loud and
    self-explaining instead.
    """
    environments = _load_basedpyright_config()["executionEnvironments"]
    exempted = {
        root
        for env in environments
        if (root := env.get("root")) is not None
        and env.get("reportPrivateUsage") is False
    }

    missing = sorted(_colocated_test_dirs() - exempted)

    assert not missing, (
        "these co-located test directories have no reportPrivateUsage "
        f"exemption in pyproject.toml: {missing}. `root` matches by directory "
        "prefix only - no glob - so each needs its own "
        "[[tool.basedpyright.executionEnvironments]] entry."
    )


def _workflow_paths() -> list[Path]:
    """Every workflow file, proven to exist before anything reads them."""
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows, "no workflow files found under .github/workflows"
    return workflows


def _guard_module_texts() -> list[tuple[str, str]]:
    """Every guard module under ``dev/guards/`` as ``(relative path, text)``."""
    modules = sorted((ROOT / "dev" / "guards").rglob("test_*.py"))
    assert modules, "no guard modules found under dev/guards"
    return [
        (path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8"))
        for path in modules
    ]


def _sentinel_workflow() -> _Workflow:
    """The main-branch CI sentinel, parsed."""
    text = (ROOT / ".github" / "workflows" / "main-ci-sentinel.yml").read_text(
        encoding="utf-8"
    )
    return cast("_Workflow", yaml.safe_load(text))


def _sentinel_step(name_fragment: str) -> _WorkflowStep:
    """The one sentinel step whose name contains *name_fragment*."""
    steps = _sentinel_workflow()["jobs"]["assert-main-was-validated"]["steps"]
    matches = [step for step in steps if name_fragment in step.get("name", "")]
    assert len(matches) == 1, (
        f"expected exactly one sentinel step named like {name_fragment!r}, "
        f"found {[step.get('name') for step in matches]}"
    )
    return matches[0]


def test_the_sentinel_closes_its_issue_only_on_a_healthy_verdict() -> None:
    """`pending` must not close the sentinel issue.

    ``Verdict.exit_code`` is 0 for ``healthy`` and for ``pending`` alike,
    because neither should fail the sentinel job. A workflow that derives
    health from that exit code therefore cannot tell "main is green" from "no
    verdict yet" - and closes on both. That is exactly what happened at
    17:25 UTC on 2026-09-04: the judge logged ``pending: 1 CI run(s) still in
    flight``, the close step ran anyway, and issue #398 was closed as
    "validated again" while main's tip was red and its CI still running.

    The condition is asserted literally rather than by behaviour because the
    failure mode is a silent one: a condition that never matches - a typo, or
    a negation such as ``!= 'unhealthy'`` that readmits ``pending`` - leaves
    the step skipped and the job green, which is indistinguishable from
    working.
    """
    step = _sentinel_step("Close the sentinel issue")

    assert step.get("if") == "${{ steps.judge.outputs.state == 'healthy' }}"


def test_the_sentinel_opens_its_issue_only_on_an_unhealthy_verdict() -> None:
    """The other half of the same contract: `pending` must not report a fault.

    A sentinel that files an issue while a run is still in flight fires on
    every push and gets muted, which leaves main less protected than if it did
    not exist.
    """
    step = _sentinel_step("Open an issue")

    assert step.get("if") == "${{ steps.judge.outputs.state == 'unhealthy' }}"


def test_the_sentinel_branches_only_on_states_the_judge_can_return() -> None:
    """Every state named in a condition must be one the module can produce.

    A misspelled state is the worst shape this workflow can take: the
    condition is valid YAML, the expression evaluates to false forever, the
    step is skipped, and the job passes. Nothing reports it.
    """
    from dev.ci_sentinel.main_ci_health import State

    known = set(get_args(State))
    steps = _sentinel_workflow()["jobs"]["assert-main-was-validated"]["steps"]
    referenced = {
        match.group("state")
        for step in steps
        for match in _SENTINEL_STATE_CONDITION.finditer(str(step.get("if", "")))
    }

    assert referenced, "no sentinel step branches on the judge's state"
    assert referenced <= known, (
        f"these sentinel conditions name states the judge never returns: "
        f"{sorted(referenced - known)}; it returns {sorted(known)}"
    )


def test_the_sentinel_does_not_derive_health_from_the_judge_exit_code() -> None:
    """No step may branch on a boolean distilled from the module's exit code.

    Keeping the states apart in the judge step is worth nothing if a later
    step collapses them again, so the collapsed output is banned by name: the
    `healthy` output that carried this bug must not come back.
    """
    steps = _sentinel_workflow()["jobs"]["assert-main-was-validated"]["steps"]

    offenders = [
        step.get("name")
        for step in steps
        if "outputs.healthy" in str(step.get("if", ""))
        or "outputs.healthy" in str(step.get("run", ""))
        or "healthy=$(" in str(step.get("run", ""))
    ]

    assert not offenders, (
        f"these sentinel steps read health from the judge's exit code rather "
        f"than its state: {offenders}. The exit code answers 'should this job "
        f"fail?', which is 0 for both `healthy` and `pending`."
    )


def test_the_sentinel_fails_when_the_judge_returns_no_verdict() -> None:
    """A judge that crashed must not read as a quiet pass.

    With the state absent, every condition below evaluates false, no step
    runs, and the sentinel reports success having judged nothing - the same
    class of silent skip the sentinel itself exists to catch.
    """
    run = _sentinel_step("Judge main's tip").get("run", "")

    assert "the sentinel produced no verdict" in run, (
        "the judge step must fail loudly when it produces no parseable state"
    )


#: The marker the pre-commit hook selects with, and the flag that selects it.
_PRECOMMIT_MARKER = "precommit"
_MARKER_SELECTOR = f"-m {_PRECOMMIT_MARKER}"


def _precommit_hook_entries() -> list[str]:
    """Every ``entry:`` line declared by a local hook in the pre-commit config."""
    config = cast(
        "_PreCommitConfig",
        yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")),
    )
    return [
        hook["entry"]
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if "entry" in hook
    ]


def test_the_markdown_guards_run_before_a_commit_not_only_in_ci() -> None:
    """The bare-reference guard must be reachable without pushing.

    It was CI-only until 2026-09-05, so ``vault check`` - a snippet naming a
    command group that is not an executable - landed in README.md on
    2026-09-02 and main stayed red for two days. The guard itself costs 0.02s
    and reads markdown; only its siblings in the same file are slow, because
    they shell out to ``--help`` for every command.

    Asserted against the config rather than against behaviour because the
    failure is silent: a deleted hook removes local coverage and breaks
    nothing that any test would otherwise notice.
    """
    entries = _precommit_hook_entries()

    assert any(_MARKER_SELECTOR in entry for entry in entries), (
        f"no pre-commit hook selects '{_MARKER_SELECTOR}', so the markdown "
        "guards run only after a push"
    )


def test_the_precommit_marker_selects_something() -> None:
    """A marker nothing carries selects nothing, and the hook stops guarding.

    pytest exits 5 on an empty selection, so the hook would fail rather than
    pass quietly - but it would fail on every markdown commit for a reason
    that reads like tooling breakage. Naming the cause here is cheaper.
    """
    marked = [
        rel
        for rel, text in _guard_module_texts()
        if f"@pytest.mark.{_PRECOMMIT_MARKER}" in text
    ]

    assert marked, (
        f"no test in dev/guards carries @pytest.mark.{_PRECOMMIT_MARKER}, so "
        "the pre-commit hook selects an empty set"
    )


def test_the_precommit_marker_never_becomes_the_ci_selection() -> None:
    """CI must keep running the whole file, marker or no marker.

    The hook is an accelerator: it runs the cheap subset early. The moment CI
    selects the same subset, the expensive guards - the ones that compare
    documentation against live ``--help`` output - stop running anywhere, and
    the marker silently converts from a speed-up into a coverage cut.
    """
    offenders: list[str] = []
    for path in _workflow_paths():
        workflow = cast("_Workflow", yaml.safe_load(path.read_text(encoding="utf-8")))
        for job_name, job in workflow["jobs"].items():
            for step in job.get("steps", []) or []:
                if _MARKER_SELECTOR in str(step.get("run", "")):
                    offenders.append(f"{path.name}:{job_name}:{step.get('name')}")

    assert not offenders, (
        f"these CI steps select '{_MARKER_SELECTOR}', which would leave the "
        f"guards outside that marker running nowhere: {offenders}"
    )
