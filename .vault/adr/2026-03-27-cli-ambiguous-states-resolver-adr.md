---
tags:
  - '#adr'
  - '#cli-ambiguous-states'
date: '2026-03-27'
related:
  - '[[2026-03-27-cli-ambiguous-states-research]]'
  - '[[2026-03-27-cli-ambiguous-states-prior-art-research]]'
  - '[[2026-03-15-install-cmds-capability-audit]]'
  - '[[2026-03-23-cli-test-coverage-research]]'
  - '[[2026-03-27-cli-ambiguous-states-gitignore-adr]]'
---

# `cli-ambiguous-states` adr: workspace state diagnosis and resolution engine | (**status:** `accepted`)

## Problem Statement

The CLI uses binary state detection: `.vaultspec/` exists or it doesn't.
The manifest (`providers.json`) tracks installed providers but provides no
integrity verification. This fails for: partial installations, corrupted
manifests, orphaned directories, stale synced content, pre-existing
provider configs, version mismatches, and mixed managed/user content.
The state space across 7 independent axes is combinatorially large
(~32,000 combinations per provider), making manual enum enumeration
impractical. GitHub issue #16.

## Considerations

- **chezmoi** proves a three-state model (source / last-written / actual)
  with SHA-256 content comparison and a `doctor` command of independent
  check functions. Closest analog to our problem space.

- **Terraform** proves plan/apply phase separation with reason codes on
  actions, state file versioning via serial counter, and in-memory
  refresh before every plan. The recorded-vs-actual-vs-desired triple
  maps directly.

- **Ansible** proves independent fact collectors with exception isolation,
  `state: present/absent` desired-state vocabulary, and the
  detect-compare-apply module pattern.

- **GNU Stow** proves conflict-accumulation-before-execution as a safety
  pattern. No filesystem mutations until all conflicts resolved.

- **pre-commit** proves hash-based ownership markers embedded in managed
  files for ownership detection without a manifest.

- **uv** proves a four-bucket diff model (cached/remote/reinstall/
  extraneous) that maps to sync result accounting.

## Constraints

- Must not break existing install/sync/uninstall CLI behavior for users
  in clean states. The resolver wraps existing commands transparently.

- Signal collectors must be pure functions with no side effects. Exception
  isolation prevents one failed collector from blocking others.

- The manifest schema change (v1.0 to v2.0) must be backward-compatible:
  the resolver must handle v1.0 manifests gracefully (treat missing fields
  as unknown/unversioned rather than erroring).

- Performance: full diagnosis must not add perceptible latency to normal
  operations. Lazy collection - only run collectors relevant to the
  requested command.

- The existing `SyncResult` accounting (added/updated/pruned/skipped/
  errors/warnings) must be preserved. The resolver feeds into, not
  replaces, the sync pipeline.

- The `_ensure_tool_configs()` bootstrap in `commands.py` creates a
  temporary directory to fake a workspace layout when `.vaultspec/`
  doesn't exist. The resolver must handle diagnosis before `init_paths`
  completes. Framework-presence and manifest-coherence collectors operate
  on raw filesystem paths and do not require `WorkspaceContext`. Only
  the content-integrity and provider-dir collectors need tool configs,
  and they are skipped when the framework signal is MISSING or CORRUPTED.
  This layered collection order resolves the chicken-and-egg problem.

## Implementation

### Signal enums (new package: `core/diagnosis/signals.py`)

Seven signal enum types, one per independent axis. Individual values are
enums; combinations are not. This keeps the enum space at ~35 total
members rather than ~32,000.

```python
class FrameworkSignal(StrEnum):
    MISSING = "missing"
    CORRUPTED = "corrupted"       # dir exists, manifest absent or malformed
    PRESENT = "present"

class ProviderDirSignal(StrEnum):
    MISSING = "missing"
    EMPTY = "empty"               # scaffolded, never synced
    PARTIAL = "partial"           # some expected files missing
    COMPLETE = "complete"         # all expected files present
    MIXED = "mixed"               # has non-vaultspec user content

class ManifestEntrySignal(StrEnum):
    COHERENT = "coherent"         # manifest and filesystem agree
    ORPHANED = "orphaned"         # in manifest, directory missing
    UNTRACKED = "untracked"       # directory exists, not in manifest
    NOT_INSTALLED = "not_installed"

class ContentSignal(StrEnum):
    CLEAN = "clean"               # file matches source transform
    DIVERGED = "diverged"         # file differs from expected content
    STALE = "stale"               # destination file has no source
    MISSING = "missing"           # source exists, no destination

class BuiltinVersionSignal(StrEnum):
    CURRENT = "current"           # matches snapshot
    MODIFIED = "modified"         # user edited builtin
    DELETED = "deleted"           # builtin removed, snapshot exists
    NO_SNAPSHOTS = "no_snapshots" # pre-version install, no baseline

class ConfigSignal(StrEnum):
    OK = "ok"                     # present, well-formed, has AUTO-GENERATED marker
    MISSING = "missing"           # config file absent
    FOREIGN = "foreign"           # config exists, no AUTO-GENERATED marker (user-authored)
    PARTIAL_MCP = "partial_mcp"   # .mcp.json missing vaultspec-core entry
    USER_MCP = "user_mcp"         # .mcp.json has extra user entries

class GitignoreSignal(StrEnum):
    NO_FILE = "no_file"
    NO_ENTRIES = "no_entries"     # file exists, no managed block
    PARTIAL = "partial"           # managed block exists, entries stale
    COMPLETE = "complete"         # managed block exists, all entries present
    CORRUPTED = "corrupted"       # only one marker found (orphaned)
```

### Resolution actions (enum, not bare string)

```python
class ResolutionAction(StrEnum):
    SCAFFOLD = "scaffold"
    SYNC = "sync"
    PRUNE = "prune"
    REPAIR_MANIFEST = "repair_manifest"
    ADOPT_DIRECTORY = "adopt_directory"
    REPAIR_GITIGNORE = "repair_gitignore"
    REMOVE = "remove"
    SKIP = "skip"
```

Using an enum enables exhaustive matching in the executor and prevents
typo bugs. The set is extensible as new resolution behaviors are needed.

### Package structure: `core/diagnosis/`

The diagnosis module is a package, not a single file, given the scope
of 7 collectors, 7+ signal enums, dataclasses, and the orchestrator:

```
core/diagnosis/
    __init__.py           # exports diagnose(), WorkspaceDiagnosis
    signals.py            # all signal enums
    collectors.py         # all collect_*() functions
    diagnosis.py          # WorkspaceDiagnosis, ProviderDiagnosis, diagnose()
```

### Signal collectors (pure functions in `core/diagnosis/collectors.py`)

Each collector inspects one axis and returns a typed signal. Modeled after
Ansible's `BaseFactCollector` with exception isolation.

```python
def collect_framework_presence(target: Path) -> FrameworkSignal
def collect_provider_dir_state(target: Path, tool: Tool) -> ProviderDirSignal
def collect_manifest_coherence(target: Path) -> dict[Tool, ManifestEntrySignal]
def collect_content_integrity(target: Path, tool: Tool) -> dict[str, ContentSignal]
def collect_builtin_version_state(target: Path) -> BuiltinVersionSignal
def collect_config_state(target: Path, tool: Tool) -> ConfigSignal
def collect_gitignore_state(target: Path) -> GitignoreSignal
```

**Collection ordering**: framework-presence and manifest-coherence
collectors run first (no `WorkspaceContext` needed - they inspect raw
filesystem paths). If framework signal is MISSING or CORRUPTED, the
content-integrity and provider-dir collectors are skipped (they require
tool configs that can't be resolved without `.vaultspec/`). This
resolves the bootstrap chicken-and-egg with `_ensure_tool_configs()`.

**Content integrity**: the collector reuses the existing sync
infrastructure. It calls the same `collect_rules()`, `collect_skills()`,
etc. and `transform_fn` callables to produce expected content, then
SHA-256 compares against actual destination files. This is effectively
a read-only dry-run sync. It only runs when explicitly needed (for
`doctor` and when the resolver detects potential drift), not on every
command invocation.

**Provider directory "expected file set"**: determined by running the
collect/transform pipeline against the current `.vaultspec/rules/`
source content. The expected set is implicit (whatever sync would
produce), not declared in a separate manifest. This avoids a second
source of truth that could itself drift.

**Shared directory diagnosis** (e.g. `.agents/` shared by gemini,
antigravity, codex): the `collect_provider_dir_state` collector
inspects only the subdirectories owned by a specific provider (e.g.
`.agents/skills/` for antigravity) rather than the shared root. The
collector cross-references `ToolConfig` to determine which paths belong
to which provider.

Content integrity comparison uses SHA-256 of the expected transformed
output vs actual file content, following chezmoi's `ContentsSHA256`
pattern. No timestamp-based comparison.

### Workspace diagnosis (aggregation dataclass)

```python
@dataclass
class ProviderDiagnosis:
    tool: Tool
    dir_state: ProviderDirSignal
    manifest_entry: ManifestEntrySignal
    content: dict[str, ContentSignal]
    config: ConfigSignal

@dataclass
class WorkspaceDiagnosis:
    framework: FrameworkSignal
    providers: dict[Tool, ProviderDiagnosis]
    builtin_version: BuiltinVersionSignal
    gitignore: GitignoreSignal
```

This is a fact-only layer. Analogous to Terraform's in-memory refresh.

### Resolution engine (new module: `core/resolver.py`)

Takes `WorkspaceDiagnosis` + requested action + flags and produces a
`ResolutionPlan` or raises `ResolutionError`.

```python
@dataclass
class ResolutionStep:
    action: ResolutionAction
    target: str          # what it acts on (provider name, file path)
    reason: str          # why this step is needed (Terraform reason code)

@dataclass
class ResolutionPlan:
    steps: list[ResolutionStep]
    warnings: list[str]  # non-blocking advisories (pre-flight)
    conflicts: list[str] # blocking issues requiring user intervention

def resolve(
    diagnosis: WorkspaceDiagnosis,
    action: str,           # "install", "sync", "uninstall", "upgrade", "doctor"
    provider: str,
    force: bool = False,
    dry_run: bool = False,
) -> ResolutionPlan
```

The `resolve()` function is called once per command invocation, not once
per provider. Provider-independent steps (e.g. `REPAIR_MANIFEST`) are
ordered before provider-specific steps (e.g. `SCAFFOLD` for a specific
provider). When `provider="all"`, the resolver iterates all providers
internally.

Follows Stow's pattern: conflicts block execution. All conflicts must be
empty for the plan to proceed to execution.

#### Full resolution rule matrix

| Signal                                      | Action                              | force=False                         | force=True |
| ------------------------------------------- | ----------------------------------- | ----------------------------------- | ---------- |
| `FrameworkSignal.MISSING` + `install`       | proceed normally                    | proceed normally                    |            |
| `FrameworkSignal.MISSING` + `sync`          | error: "not installed"              | error: "not installed"              |            |
| `FrameworkSignal.MISSING` + `uninstall`     | warning: "nothing to remove"        | warning: "nothing to remove"        |            |
| `FrameworkSignal.CORRUPTED` + `install`     | conflict: "corrupted manifest"      | step: `REPAIR_MANIFEST`             |            |
| `FrameworkSignal.CORRUPTED` + `sync`        | step: `REPAIR_MANIFEST` then `SYNC` | step: `REPAIR_MANIFEST` then `SYNC` |            |
| `ManifestEntrySignal.ORPHANED` + `sync`     | step: `SCAFFOLD` then `SYNC`        | step: `SCAFFOLD` then `SYNC`        |            |
| `ManifestEntrySignal.UNTRACKED` + `install` | step: `ADOPT_DIRECTORY`             | step: `ADOPT_DIRECTORY`             |            |
| `ManifestEntrySignal.UNTRACKED` + `sync`    | warning: "untracked dir"            | step: `ADOPT_DIRECTORY` then `SYNC` |            |
| `ProviderDirSignal.MIXED` + `uninstall`     | conflict: "user content"            | step: `REMOVE`                      |            |
| `ProviderDirSignal.EMPTY` + `sync`          | step: `SYNC`                        | step: `SYNC`                        |            |
| `ProviderDirSignal.PARTIAL` + `sync`        | step: `SYNC` (additive)             | step: `SYNC` (full)                 |            |
| `ContentSignal.STALE` + `sync`              | warning: "stale file"               | step: `PRUNE`                       |            |
| `ContentSignal.MISSING` + `sync`            | step: `SYNC` (add missing)          | step: `SYNC` (add missing)          |            |
| `ContentSignal.DIVERGED` + `sync`           | warning: "diverged file"            | step: `SYNC` (overwrite)            |            |
| `BuiltinVersionSignal.MODIFIED` + `sync`    | warning: "builtins modified"        | step: `SYNC` (re-seed)              |            |
| `BuiltinVersionSignal.NO_SNAPSHOTS` + any   | warning: "no version baseline"      | warning: "no version baseline"      |            |
| `ConfigSignal.MISSING` + `sync`             | step: `SYNC` (regenerate)           | step: `SYNC` (regenerate)           |            |
| `ConfigSignal.FOREIGN` + `sync`             | warning: "user-authored config"     | step: `SYNC` (overwrite)            |            |
| `GitignoreSignal.NO_ENTRIES` + `install`    | step: `REPAIR_GITIGNORE`            | step: `REPAIR_GITIGNORE`            |            |
| `GitignoreSignal.CORRUPTED` + any           | step: `REPAIR_GITIGNORE`            | step: `REPAIR_GITIGNORE`            |            |

#### Warning semantics

`ResolutionPlan.warnings` are pre-flight advisories emitted before
execution. `SyncResult.warnings` are post-sync advisories emitted during
sync passes. Both surface to the user in sequence: resolution warnings
first, then sync warnings. They are not merged - they serve different
phases.

### Guard migration strategy

The existing inline guards in `commands.py` (`sync_provider` lines
882-887 for workspace existence, lines 922-927 for manifest membership)
are preserved as defense-in-depth but demoted to assertions. The resolver
pre-flight is the primary check. This means:

- Direct callers (`install_run`, tests) still get guard protection
- The resolver catches the same conditions earlier and with richer context
- No code removal required in the initial implementation
- Guards can be removed in a later cleanup pass once the resolver is
  proven stable

### Manifest v2.0

Backward-compatible extension of `providers.json`:

```json
{
  "version": "2.0",
  "vaultspec_version": "0.1.4",
  "installed_at": "2026-03-27T10:00:00Z",
  "serial": 1,
  "installed": ["claude", "gemini"],
  "provider_state": {
    "claude": {
      "installed_at": "2026-03-27T10:00:00Z",
      "last_synced": "2026-03-27T10:05:00Z"
    }
  },
  "gitignore_managed": false
}
```

- `serial`: monotonic counter, incremented on every write. Advisory-only
  for diagnostics (not enforced via locking). For a single-user CLI tool,
  strict CAS is not needed; the serial detects accidental concurrent
  edits and surfaces them in `doctor` output. The new `write_manifest()`
  reads the current serial and increments it.
- `vaultspec_version`: package version that last wrote the manifest.
  When the running version is older than the recorded version, the
  resolver emits a warning ("manifest written by newer vaultspec-core").
  It does not refuse to proceed.
- `provider_state`: per-provider install/sync timestamps. `last_synced`
  records the last *attempted* sync start time, not a guarantee of
  completeness. Content integrity checks provide the actual completeness
  signal.
- `gitignore_managed`: tracks whether managed block was created (respects
  user removal, see ADR 2).

**Dropped from initial research proposal**: `lineage` (UUID) and
`layout_version` are deferred. `lineage` has no concrete trigger for
local-only manifests. `layout_version` is speculative until a layout
migration actually ships. The `version` field ("2.0") serves as the
schema version.

Reading logic: if `version` is `"1.0"` or absent, treat all new fields as
their zero-values. No migration step required - the next write upgrades
the schema automatically.

**Manifest data structure**: `write_manifest()` is updated to accept a
`ManifestData` dataclass rather than just `set[str]`:

```python
@dataclass
class ManifestData:
    version: str = "2.0"
    vaultspec_version: str = ""
    installed_at: str = ""
    serial: int = 0
    installed: set[str] = field(default_factory=set)
    provider_state: dict[str, dict[str, str]] = field(default_factory=dict)
    gitignore_managed: bool = False
```

Convenience functions (`add_providers`, `remove_provider`) are preserved
as wrappers that read the full `ManifestData`, mutate, and write back.

### Content ownership markers

Formalize the existing `AUTO-GENERATED` header for ownership detection:

- Root configs (`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`): the existing
  `<!-- AUTO-GENERATED by cli.py config sync. -->` header becomes the
  canonical ownership marker. `ConfigSignal.FOREIGN` is emitted when the
  config exists but this marker is absent, distinguishing "user replaced
  our config" from "config is missing."

- Synced rule files: already carry `.builtin.md` suffix for builtins.
  User-authored rules in provider `rules/` directories lack this suffix
  and are expected user content - they do not trigger MIXED.

- Synced skill directories: contain `SKILL.md` entrypoints sourced from
  `.vaultspec/rules/skills/`. Ownership determined by presence in the
  source directory.

- MIXED signal: triggered only by unexpected content types in provider
  directories (e.g. non-.md files, directories that don't match any known
  resource pattern). User-authored rules and skills are expected and do
  not trigger MIXED.

### CLI integration: `vaultspec-core doctor`

New top-level command that runs full diagnosis and reports results.
Modeled after `chezmoi doctor`:

```
$ vaultspec-core doctor
  framework        ok     .vaultspec/ present, manifest v2.0
  claude           ok     directory complete, manifest coherent
  gemini           warn   directory partial (2 files missing)
  antigravity      ok     directory complete, manifest coherent
  codex            error  manifest orphaned (directory missing)
  builtins         warn   2 modified since install
  gitignore        info   no managed block
  mcp              ok     .mcp.json present
```

The `doctor` command supports `--json` for CI/scripting:

```
$ vaultspec-core doctor --json
{"framework": {"signal": "present", ...}, ...}
```

Exit codes: 0 if all signals are ok/info, 1 if any warnings, 2 if any
errors or conflicts. The JSON output includes the full
`WorkspaceDiagnosis` serialized.

### Test strategy

Direct callers (`install_run`, `sync_provider`, `uninstall_run`) remain
callable standalone. Existing tests continue to work without going
through the resolver. New tests exercise the resolver path. This allows
incremental adoption:

- Phase 1: diagnosis + doctor command (no resolver pre-flight)
- Phase 2: resolver pre-flight wired into CLI handlers
- Phase 3: inline guards demoted to assertions

## Rationale

- **Signal-based over enum-based**: combinatorial state space makes
  exhaustive enumeration impractical. All six prior art tools decompose
  state into independent axes. This is the consensus approach.

- **Plan/apply separation**: proven by Terraform and Stow. Prevents
  partial filesystem mutations on unexpected states. Enables `--dry-run`
  and `doctor` as natural byproducts.

- **Manifest v2.0 with serial**: Terraform's state versioning is
  battle-tested for detecting concurrent writes. Advisory-only serial
  is appropriate for a single-user CLI. Dropped `lineage` and
  `layout_version` as speculative complexity.

- **Content SHA-256 over timestamps**: chezmoi proves this is reliable
  across platforms and avoids timezone/clock-skew issues.

- **Conflict accumulation**: Stow proves this prevents the "half-mutated
  workspace" failure mode that currently exists when sync encounters
  unexpected files.

- **Ownership markers over heuristics**: pre-commit proves explicit
  markers are more reliable than inferring ownership from file content
  patterns.

- **Package over single module**: reviewers correctly identified that 7
  collectors + 7 enums + dataclasses + orchestrator exceeds single-file
  scope.

- **Enum actions over bare strings**: prevents typo bugs and enables
  exhaustive matching in the executor.

## Consequences

- **New package**: `core/diagnosis/` (3 modules, ~500-600 lines total)
  and `core/resolver.py` (~200-300 lines). Moderate addition.

- **Manifest schema change**: v1.0 manifests are silently upgraded on
  next write. No migration tool needed. Old vaultspec-core versions
  will ignore new fields but won't corrupt them (they only read
  `installed`).

- **Test surface**: new tests for the resolver and diagnosis are
  additive. Existing tests are unaffected. The resolver requires
  parametrized test fixtures for each signal combination. ~12 key
  scenarios identified in the research. Test complexity is proportional
  to signal axes (linear), not combinations (exponential).

- **Performance**: lazy collection means normal operations add only the
  collectors relevant to the requested command. Content integrity
  (the most expensive collector) only runs for `doctor` and
  explicit drift checks.

- **Guard deprecation path**: inline guards are preserved initially,
  allowing phased rollout without breaking existing callers.

- **Dependency on ADR 2**: the `GitignoreSignal` collector and its
  resolution rules depend on the gitignore managed block ADR for the
  specific marker format and insertion algorithm.
