"""The declarative registry of development verbs and their targets.

This module is the single source of truth for what the harness can do. The
``justfile`` exposes each verb; everything about *what a target runs*, whether
it gates, and how targets compose into aggregates is stated here as data.

The verbs split by CONSEQUENCE, not by tool:

``lint``
    GATES. Read-only, and a finding fails the build.
``fix``
    MUTATES. Everything automatically repairable, in one pass.
``audit``
    Only ``deps`` gates. Every other target is advisory and exits 0 even with
    findings, because each yields a lead to confirm rather than a verdict.
``test``
    GATES. See :data:`TEST` for what each lane proves.
"""

from __future__ import annotations

from dataclasses import dataclass

from dev.runner import Cmd, Echo, Ref, Step, ToolOrDocker, uv_run

PACKAGE = "src/vaultspec_core"

#: The code-health instrument, named once because all three `health` targets
#: run the same script and differ only in the flag they pass it.
HEALTH_REPORT = "dev/health/health_report.py"

#: Python trees that carry committed source and are therefore linted. Every
#: development instrument the harness invokes - the release builder, the
#: supply-chain gate, the code-health report, the transcript analytics - now
#: lives under `dev`, and the documentation-asset renderers live beside the
#: assets they write, under `docs`. Naming those two trees covers what four
#: separate root folders used to, and none of them can lint itself into an
#: exception by sitting outside the list.
#:
#: `tests` is absent because the repository root no longer carries one: the
#: repo-wide contract guards that lived there moved to `dev/guards`, so they
#: are linted by the `dev` entry along with everything else in that tree.
PYTHON_PATHS = ("src", "dev", "docs")

#: Trees carrying an instrument and its cohabiting guards. `harness` runs them
#: as one lane, and `testpaths` in pyproject.toml names the same two, so the
#: default `pytest` invocation and the gate cannot disagree about the suite.
INSTRUMENT_PATHS = ("dev", "docs")

#: Markers requiring an external CLI or credentials, excluded from every gate.
EXCLUDED_MARKERS = "not claude"

#: What a lane testing the LIBRARY selects. The two populations in this suite
#: are told apart by marker, not by directory: `repo` tests assert facts about
#: this checkout - the workflow contracts, the packaging metadata, the shipped
#: templates, the `typings/` stubs - and are meaningless outside a source tree,
#: while everything else exercises `vaultspec_core` itself and must never know a
#: repository exists.
#:
#: Excluding `repo` by MARKER rather than by path is the load-bearing part. A
#: repository-health guard still filed under `src` - and the audit of that
#: boundary is finding them - is correctly kept out of `unit` and `broad` and
#: correctly picked up by the `repo` lane the moment it is marked, before it is
#: moved anywhere. Relocating it afterwards is then a move, with no lane to
#: re-plumb.
LIBRARY_MARKERS = f"not repo and {EXCLUDED_MARKERS}"

#: Trees whose Markdown is formatted and linted. The four root READMEs are named
#: individually rather than by their enclosing directory - `dev/`, `src/`, and
#: `typings/` each cohabit with non-Markdown trees (and `dev/` cohabits with test
#: fixture Markdown that documents a *format*, not a repository surface, and must
#: not be held to this gate) - so naming the file is what scopes the gate to the
#: convention it enforces without also picking up what happens to sit nearby.
MARKDOWN_PATHS = (
    "README.md",
    "docs/",
    ".vault/",
    "src/vaultspec_core/builtins/",
    "dev/README.md",
    "src/README.md",
    "typings/README.md",
)

#: User-facing Markdown additionally held to a hard wrap. The root READMEs added
#: above to `MARKDOWN_PATHS` are deliberately absent here: each describes a
#: contributor-facing repository surface - the dev harness, the distributed
#: package's internal test layout, third-party type stubs -
#: read by someone with a checkout, not the shipped-to-users prose (the project's
#: front door, the linked doc pages, the builtins a consumer's install renders)
#: this list holds to a fixed column width.
#:
#: `docs/` is named as a DIRECTORY rather than as the four pages this tuple used
#: to list. Every file under it is a linked, user-facing page - `docs/README.md`
#: is the index for the rest - so enumerating them added nothing a reader could
#: not see, and cost the width rule five pages it should have covered:
#: `correctness`, `verification`, `examples`, `syntax`, and the index itself
#: were formatted by the unwrapped pass above and checked at no width at all.
#: `docs/assets/` holds images only, so the directory needs no exclusion.
#:
#: A hand-kept list that falls behind the tree it describes is the same defect
#: this repository keeps finding elsewhere - the release workflow derives its
#: expected build targets from its own matrix for exactly this reason.
WRAPPED_MARKDOWN = (
    "README.md",
    "docs/",
    "src/vaultspec_core/builtins",
)

#: complexipy emits status glyphs; Windows consoles default to a codepage that
#: cannot encode them, which aborts the run before any finding is reported.
UTF8 = {"PYTHONIOENCODING": "utf-8"}

#: Repairing the corpus is reachable as both `fix vault` and `vault fix`, which
#: are the same action approached from the two verbs a reader might try. The
#: steps are defined once here so the two entry points cannot drift.
VAULT_FIX_STEPS = (
    uv_run("vaultspec-core", "vault", "check", "all", "--fix"),
    uv_run("vaultspec-core", "vault", "sanitize", "annotations"),
)


@dataclass(frozen=True)
class Target:
    """One selectable behaviour within a verb.

    Args:
        name: The target token typed on the command line.
        summary: One-line description shown by ``help``.
        steps: The steps to run, in order.
        advisory: When true the target reports findings but always exits 0.
        keep_going: When true a failing step does not stop the remaining
            steps. Aggregate dashboards set this so one red dimension does
            not hide every dimension after it.
    """

    name: str
    summary: str
    steps: tuple[Step, ...]
    advisory: bool = False
    keep_going: bool = False


@dataclass(frozen=True)
class Verb:
    """A top-level harness verb and the targets it dispatches to.

    Args:
        name: The verb token, matching the justfile recipe name.
        summary: One-line description of the verb.
        targets: The selectable targets, in display order.
        note: Optional extra line appended to the verb's ``help`` output.
    """

    name: str
    summary: str
    targets: tuple[Target, ...]
    note: str = ""

    def target_names(self) -> tuple[str, ...]:
        """Return every target token in display order."""
        return tuple(target.name for target in self.targets)

    def find(self, name: str) -> Target | None:
        """Return the named target, or ``None`` when it is not defined."""
        return next((t for t in self.targets if t.name == name), None)


def _ruff_paths(*prefix: str) -> Cmd:
    return uv_run("ruff", *prefix, *PYTHON_PATHS)


DEPS = Verb(
    name="deps",
    summary="Manage project dependencies and the lockfile.",
    targets=(
        Target(
            "sync",
            "Install the locked dependency set.",
            (Cmd(("uv", "sync", "--locked", "--group", "dev")),),
        ),
        Target(
            "upgrade",
            "Upgrade every dependency group.",
            (Cmd(("uv", "sync", "--upgrade", "--all-groups")),),
        ),
        Target("lock", "Regenerate the lockfile.", (Cmd(("uv", "lock")),)),
        Target(
            "lock-upgrade",
            "Regenerate the lockfile at the newest allowed versions.",
            (Cmd(("uv", "lock", "--upgrade")),),
        ),
        Target(
            "check",
            "Verify the lockfile matches pyproject.toml.",
            (Cmd(("uv", "lock", "--check")),),
        ),
    ),
)

LINT = Verb(
    name="lint",
    summary="Run gating static analysis.",
    note=(
        "'all' omits complexity, nesting, and size - run those by name. "
        "Each is a real gate whose burndown is unfinished, so adding it to the chain "
        "would hide every dimension behind it."
    ),
    targets=(
        Target(
            "python",
            "Ruff lint and format verification.",
            (_ruff_paths("check"), _ruff_paths("format", "--check")),
        ),
        Target(
            "type",
            "Ty type checking.",
            (uv_run("python", "-m", "ty", "check", *PYTHON_PATHS),),
        ),
        # `type` above checks whichever platform it runs on, so a Windows
        # contributor's green is not Linux's green: this repository carries
        # both `msvcrt`/`ctypes.WinDLL` and `fcntl` paths, and a
        # platform-specific attribute resolves on one OS and not the other.
        # CI runs Linux, so unguarded Windows-only code passed every local
        # gate and failed only after push - the exact "green here, red
        # there" split a gate exists to prevent. Checking all three targets
        # makes the local run reproduce CI regardless of the host.
        Target(
            "type-platforms",
            "Ty type checking against every target platform.",
            tuple(
                uv_run(
                    "python",
                    "-m",
                    "ty",
                    "check",
                    "--python-platform",
                    plat,
                    *PYTHON_PATHS,
                )
                for plat in ("linux", "darwin", "win32")
            ),
        ),
        Target(
            "toml",
            "Taplo TOML linting.",
            (ToolOrDocker("taplo", ("lint", "*.toml"), "tamasfe/taplo:0.9"),),
        ),
        Target(
            "links",
            "Lychee link checking.",
            (
                ToolOrDocker(
                    "lychee",
                    (
                        "--config",
                        "lychee.toml",
                        "README.md",
                        "docs",
                        ".vault",
                        f"{PACKAGE}/builtins",
                    ),
                    "lycheeverse/lychee:latest",
                    (
                        "--config",
                        "/repo/lychee.toml",
                        "README.md",
                        "docs",
                        ".vault",
                        f"{PACKAGE}/builtins",
                    ),
                ),
            ),
        ),
        Target(
            "markdown",
            "Markdown formatting and style verification.",
            (
                uv_run("mdformat", "--check", *MARKDOWN_PATHS),
                uv_run("mdformat", "--wrap", "88", "--check", *WRAPPED_MARKDOWN),
                uv_run(
                    "pymarkdown",
                    "--config",
                    ".pymarkdown.json",
                    "scan",
                    "-r",
                    *MARKDOWN_PATHS,
                ),
            ),
        ),
        Target(
            "workflow",
            "Actionlint GitHub workflow checking.",
            (ToolOrDocker("actionlint", (), "rhysd/actionlint:latest"),),
        ),
        Target(
            "complexity",
            "Cognitive complexity over production code.",
            (Cmd(uv_run("complexipy", PACKAGE).argv, UTF8),),
        ),
        Target(
            "nesting",
            "Nesting depth (PLR1702, preview-scoped).",
            (uv_run("ruff", "check", "src", "--select", "PLR1702", "--preview"),),
        ),
        Target(
            "size",
            "Module length and class design limits ruff has no rule for.",
            (
                uv_run(
                    "pylint",
                    PACKAGE,
                    "--rcfile=pyproject.toml",
                    "--recursive=y",
                    "--score=n",
                ),
            ),
        ),
        Target(
            "type-strict",
            "Basedpyright strict-mode type checking.",
            (uv_run("basedpyright"),),
        ),
        Target(
            "all",
            "Every gate that is green and can hold that line.",
            # complexity/nesting/size joined this aggregate once each went green
            # and held: the governing ADR's promotion rule is that a dimension
            # graduates when its finding count reaches zero at the gate's
            # threshold. Until they did, `just lint` covered six of ten
            # dimensions while CI ran the other four as separate steps, so a
            # contributor could push a complexity regression and only learn
            # about it from CI. A local gate that omits what CI enforces
            # teaches people the wrong thing about what "green" means.
            #
            # `type-strict` joined the same way: the burndown reached zero, so
            # the dimension graduated into the chain under the same promotion
            # rule the other dimensions followed.
            tuple(
                Ref(name)
                for name in (
                    "python",
                    "type",
                    "type-platforms",
                    "toml",
                    "links",
                    "markdown",
                    "workflow",
                    "complexity",
                    "nesting",
                    "size",
                    "type-strict",
                )
            ),
        ),
    ),
)

FIX = Verb(
    name="fix",
    summary="Apply every available formatter and automatic fix.",
    targets=(
        Target(
            "python",
            "Format and auto-repair Python source.",
            (_ruff_paths("format"), _ruff_paths("check", "--fix")),
        ),
        Target(
            "toml",
            "Format TOML files.",
            (ToolOrDocker("taplo", ("fmt", "*.toml"), "tamasfe/taplo:0.9"),),
        ),
        Target(
            "markdown",
            "Format and auto-repair Markdown.",
            (
                uv_run("mdformat", *MARKDOWN_PATHS),
                uv_run("mdformat", "--wrap", "88", *WRAPPED_MARKDOWN),
                uv_run(
                    "pymarkdown",
                    "--config",
                    ".pymarkdown.json",
                    "fix",
                    "-r",
                    *MARKDOWN_PATHS,
                ),
            ),
        ),
        Target(
            "vault",
            "Repair this repository's own .vault/ corpus.",
            VAULT_FIX_STEPS,
        ),
        Target(
            "all",
            "Run every fixer.",
            tuple(Ref(name) for name in ("python", "toml", "markdown", "vault")),
        ),
    ),
)

AUDIT = Verb(
    name="audit",
    summary="Audit dependencies and code quality; only 'deps' gates.",
    note=(
        "Only 'deps' gates - a published advisory against a pinned version is a "
        "verdict. Every other target is advisory and exits 0 even with findings."
    ),
    targets=(
        Target(
            "deps",
            "Dependency vulnerability audit (GATES).",
            (Cmd(("uv", "run", "python", "dev/audit/dependency_audit.py")),),
        ),
        Target(
            "security",
            "Bandit security scan.",
            (
                uv_run(
                    "bandit",
                    "-c",
                    "pyproject.toml",
                    "-r",
                    PACKAGE,
                    "-x",
                    "*/tests/*",
                    "-q",
                ),
            ),
            advisory=True,
        ),
        Target(
            "dead-code", "Vulture dead-code scan.", (uv_run("vulture"),), advisory=True
        ),
        Target(
            "dependencies",
            "Deptry dependency-drift scan.",
            (uv_run("deptry", PACKAGE),),
            advisory=True,
        ),
        Target(
            "complexity",
            "Cognitive complexity over the test tree.",
            (Cmd(uv_run("complexipy", f"{PACKAGE}/tests").argv, UTF8),),
            advisory=True,
        ),
        Target(
            "all",
            "Every audit dimension, as a dashboard.",
            (
                Echo("=== dependency advisories ==="),
                Ref("deps"),
                Echo("=== security ==="),
                Ref("security"),
                Echo("=== dead code ==="),
                Ref("dead-code"),
                Echo("=== undeclared dependencies ==="),
                Ref("dependencies"),
                Echo("=== test-tree cognitive complexity ==="),
                Ref("complexity"),
            ),
            advisory=True,
            keep_going=True,
        ),
    ),
)

TEST = Verb(
    name="test",
    summary="Run the project test suites.",
    note=(
        "'unit' is marker-scoped and selects a slice, not the suite - a green 'unit' "
        "says nothing about the far larger population 'broad' runs."
    ),
    targets=(
        Target(
            "unit",
            "The fast marker-scoped gate; first failure aborts.",
            (
                uv_run(
                    "pytest",
                    PACKAGE,
                    "-x",
                    "-q",
                    "--tb=short",
                    "-m",
                    f"unit and {LIBRARY_MARKERS}",
                ),
            ),
        ),
        Target(
            "broad",
            "The whole package suite minus credential-gated markers.",
            (uv_run("pytest", PACKAGE, "-q", "--tb=short", "-m", LIBRARY_MARKERS),),
        ),
        Target(
            "vault-repair",
            "The Windows repair and case-rename regression cohort.",
            (
                uv_run(
                    "pytest",
                    f"{PACKAGE}/tests/cli/test_vault_repair.py",
                    f"{PACKAGE}/vaultcore/checks/tests/test_structure_case_rename.py",
                    "-q",
                    "--tb=short",
                ),
            ),
        ),
        Target(
            "benchmark",
            "The slow scale benchmarks, deselected by default.",
            (uv_run("pytest", PACKAGE, "-q", "--tb=short", "-m", "benchmark"),),
        ),
        Target(
            "harness",
            "The dev/ and docs/ development-instrument guards.",
            # Every instrument guard runs in ONE lane rather than one lane per
            # instrument, because they all guard the same surface: each
            # instrument is invoked BY this registry, and the drift it can
            # suffer - a moved script, a flag the recipe passes and the
            # instrument rejects - is only visible when the registry and the
            # instrument are read together. The CI job that runs the code-health
            # report is advisory and cannot fail, so this lane is the only place
            # that disagreement gates.
            #
            # Naming the two trees rather than each `tests` package inside them
            # is deliberate: a new instrument gets its guards run by existing
            # here, instead of by someone remembering to extend a list.
            #
            # `not repo` keeps this lane to the instrument guards. The
            # repository-health guards also live under `dev`, but what they
            # assert has nothing to do with an instrument, and the `repo` lane
            # below collects them wherever they sit. Without this the two lanes
            # would overlap on `dev/guards` and a repo-health failure would be
            # reported by a lane whose name says it measures something else.
            (
                uv_run(
                    "pytest",
                    *INSTRUMENT_PATHS,
                    "-q",
                    "--tb=short",
                    "-m",
                    f"not repo and {EXCLUDED_MARKERS}",
                ),
            ),
        ),
        Target(
            "repo",
            "The repository-health guards, selected by marker across every tree.",
            # Selected by MARKER over every tree that carries committed Python,
            # not by naming a directory. A repository-health guard is defined by
            # what it asserts, not by where it sits, and this suite has already
            # paid for the other approach twice: a repository-root `tests/` tree
            # whose lane nothing invoked, and repository guards still filed
            # inside the package. Marking one is enough to gate it correctly
            # from either place, so moving it later needs no change here.
            (
                uv_run(
                    "pytest",
                    *PYTHON_PATHS,
                    "-q",
                    "--tb=short",
                    "-m",
                    f"repo and {EXCLUDED_MARKERS}",
                ),
            ),
        ),
        Target(
            "all",
            "The broad suite, vault-repair cohort, harness guards, and repo health.",
            # `repo` is in this aggregate deliberately. The lane it replaces was
            # reachable only by naming it, and no CI job named it either, so the
            # guards it runs went unobserved and the test-doubles check among
            # them had been failing undetected. A guard nothing runs is not a
            # guard, so this lane is wired into both the aggregate and CI.
            (Ref("broad"), Ref("vault-repair"), Ref("harness"), Ref("repo")),
        ),
    ),
)

BUILD = Verb(
    name="build",
    summary="Build the Python distribution artifacts.",
    note="The standalone binaries are 'just binaries <tag> <rust-target>'.",
    targets=(
        Target("python", "Build the wheel and sdist.", (Cmd(("uv", "build")),)),
        Target("all", "Run every build.", (Ref("python"),)),
    ),
)

VAULT = Verb(
    name="vault",
    summary="Operate on this repository's own .vault/ development corpus.",
    targets=(
        Target(
            "check",
            "Run the vault health checks.",
            (uv_run("vaultspec-core", "vault", "check", "all"),),
        ),
        Target("fix", "Repair and sanitize the corpus.", VAULT_FIX_STEPS),
        Target(
            "graph",
            "Render the document graph with metrics.",
            (uv_run("vaultspec-core", "vault", "graph", "--metrics"),),
        ),
        Target(
            "index",
            "Regenerate the auto-generated feature indexes.",
            (uv_run("vaultspec-core", "vault", "feature", "index"),),
        ),
        Target(
            "list",
            "List every vault document.",
            (uv_run("vaultspec-core", "vault", "list"),),
        ),
        Target(
            "stats",
            "Show corpus statistics.",
            (uv_run("vaultspec-core", "vault", "stats"),),
        ),
        Target(
            "status",
            "Show in-flight plan orientation.",
            (uv_run("vaultspec-core", "status"),),
        ),
    ),
)

FRAMEWORK = Verb(
    name="framework",
    summary="Operate on this repository's own .vaultspec/ framework harness.",
    note=(
        "'uninstall' is deliberately absent: .vaultspec/ here is the canonical "
        "framework source, not a consumer's installed copy."
    ),
    targets=(
        Target(
            "doctor",
            "Diagnose workspace health, failing on errors.",
            (uv_run("vaultspec-core", "spec", "doctor", "--gate-errors"),),
        ),
        Target(
            "install",
            "Rebuild the install manifest from tracked config.",
            (uv_run("vaultspec-core", "install", "--force"),),
        ),
        Target(
            "upgrade",
            "Refresh the installed builtin snapshots.",
            (uv_run("vaultspec-core", "install", "--upgrade"),),
        ),
        Target(
            "sync",
            "Regenerate the provider outputs.",
            (uv_run("vaultspec-core", "sync"),),
        ),
        Target(
            "reference",
            "Regenerate the bundled CLI reference.",
            (uv_run("vaultspec-core", "spec", "reference", "generate"),),
        ),
        Target(
            "reference-check",
            "Verify the bundled CLI reference is current.",
            (uv_run("vaultspec-core", "spec", "reference", "generate", "--check"),),
        ),
        Target(
            "providers",
            "Guard against committing provider artifacts.",
            (uv_run("vaultspec-core", "check-providers"),),
        ),
    ),
)

DOCS = Verb(
    name="docs",
    summary="Regenerate the committed documentation assets under docs/assets/.",
    note=(
        "Both renderers drive real commands against a throwaway synthetic vault, "
        "and both are invoked as modules rather than file paths so the demo "
        "renderer's import of its sibling resolves by its real dotted name."
    ),
    targets=(
        Target(
            "renders",
            "Regenerate the terminal-render SVGs.",
            (uv_run("python", "-m", "docs._render.render_readme_assets"),),
        ),
        Target(
            "demo",
            "Regenerate the pipeline demo GIF (needs agg on PATH).",
            (uv_run("python", "-m", "docs._render.render_readme_demo"),),
        ),
        Target(
            "all",
            "Regenerate every documentation asset.",
            (Ref("renders"), Ref("demo")),
        ),
    ),
)

HEALTH = Verb(
    name="health",
    summary="Rank the worst offenders across every code-health dimension.",
    note=(
        "MEASUREMENT ONLY - every target exits 0. This composes the gates rather "
        "than re-implementing any threshold, so the report and the gate can never "
        "disagree. 'census' regenerates the distributions each baseline ratchet in "
        "pyproject.toml is calibrated from; run it before lowering a threshold so "
        "the new value is a measurement rather than a guess."
    ),
    targets=(
        Target(
            "report",
            "Worst offenders per dimension, including strict types.",
            (Cmd(uv_run("python", HEALTH_REPORT).argv, UTF8),),
            advisory=True,
        ),
        Target(
            "fast",
            "The same report without the basedpyright section.",
            (Cmd(uv_run("python", HEALTH_REPORT, "--fast").argv, UTF8),),
            advisory=True,
        ),
        Target(
            "census",
            "Baseline-calibration distributions for the ratchet thresholds.",
            (Cmd(uv_run("python", HEALTH_REPORT, "--census").argv, UTF8),),
            advisory=True,
        ),
    ),
)

CI = Verb(
    name="ci",
    summary="Run the full local gate.",
    targets=(
        Target(
            "all",
            "Lint, dependency audit, vault checks, and the broad test suite.",
            (
                Echo("=== lint ==="),
                Cmd(("uv", "run", "--no-sync", "python", "-m", "dev", "lint", "all")),
                Echo("=== dependency audit ==="),
                Cmd(("uv", "run", "--no-sync", "python", "-m", "dev", "audit", "deps")),
                Echo("=== vault ==="),
                Cmd(
                    ("uv", "run", "--no-sync", "python", "-m", "dev", "vault", "check")
                ),
                Echo("=== tests ==="),
                Cmd(("uv", "run", "--no-sync", "python", "-m", "dev", "test", "broad")),
            ),
        ),
    ),
)

#: Every verb, in the order ``help`` lists them.
VERBS: tuple[Verb, ...] = (
    DEPS,
    LINT,
    FIX,
    AUDIT,
    TEST,
    BUILD,
    VAULT,
    FRAMEWORK,
    DOCS,
    HEALTH,
    CI,
)

#: Default target per verb, used when the justfile passes none.
DEFAULTS: dict[str, str] = {
    "deps": "sync",
    "lint": "all",
    "fix": "all",
    "audit": "all",
    "test": "all",
    "build": "python",
    "vault": "check",
    "framework": "doctor",
    "docs": "all",
    "health": "report",
    "ci": "all",
}


def find_verb(name: str) -> Verb | None:
    """Return the named verb, or ``None`` when it is not defined.

    Args:
        name: The verb token to resolve.

    Returns:
        The matching :class:`Verb`, or ``None``.
    """
    return next((verb for verb in VERBS if verb.name == name), None)


def public_targets(verb: Verb) -> tuple[str, ...]:
    """Return a verb's user-selectable target names.

    Targets whose name begins with an underscore are internal composition
    helpers and are hidden from help output.

    Args:
        verb: The verb to inspect.

    Returns:
        The public target tokens in display order.
    """
    return tuple(name for name in verb.target_names() if not name.startswith("_"))
