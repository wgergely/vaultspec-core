---
tags:
  - '#research'
  - '#cli-ambiguous-states'
date: '2026-03-27'
related:
  - '[[2026-03-15-install-cmds-capability-audit]]'
  - '[[2026-03-23-cli-test-coverage-research]]'
  - '[[2026-03-23-cli-architecture-research]]'
  - '[[2026-03-27-cli-ambiguous-states-prior-art-research]]'
---

# `cli-ambiguous-states` research: workspace state detection matrix

Research into how the CLI should detect, classify, and resolve ambiguous
workspace states across provider installations. Driven by GitHub issue #16.
Grounded against mature CLI tools: chezmoi, Terraform, Ansible, uv,
GNU Stow, pre-commit, conda.

## Problem statement

The CLI currently uses binary state detection: either `.vaultspec/` exists
(installed) or it doesn't (not installed). The manifest
(`providers.json`) tracks which providers are installed but provides no
integrity verification. This creates a large space of unhandled states
where the CLI either crashes, produces incorrect results, or silently
corrupts workspace state.

## Current state detection model

The CLI checks exactly three things before acting:

- `.vaultspec/` directory existence (install guard)
- `providers.json` content - set of installed provider names (sync/uninstall guard)
- `providers_sharing_dir()` / `providers_sharing_file()` - co-dependency check (uninstall guard)

No integrity checks exist for:

- Whether provider directories actually contain expected files
- Whether synced files match their source content
- Whether manifest reflects filesystem reality
- Whether builtins match their snapshot versions
- Whether `.mcp.json` is present and well-formed
- Whether root config files (`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`) exist
- Whether gitignore entries are present for managed paths

## Prior art analysis

### chezmoi - three-state comparison with persistent tracking

chezmoi maintains three distinct states per managed entry: **source state**
(desired), **destination state** (actual on disk), and **last-written
state** (persisted in BoltDB). This enables three-way drift detection.

Key patterns applicable to vaultspec:

- **`EntryState` type** carries `Type` (dir/file/symlink/remove/script),
  `Mode`, and `ContentsSHA256`. A nil EntryState means "absent". The
  `Equivalent()` method handles nil-as-absent cleanly.

- **`chezmoi status` output** uses a two-column format: column 1 compares
  last-written vs actual (local edits), column 2 compares actual vs
  desired (pending sync). Status codes: `A` (add), `M` (modify), `D`
  (delete), `R` (run), (space) (clean). This directly maps to vaultspec's
  content integrity axis.

- **`chezmoi doctor` command** runs an ordered list of independent check
  functions, each returning `ok`/`info`/`warning`/`error`/`skipped`.
  This validates the independent-collector architecture.

- **Pre-existing file handling**: chezmoi silently overwrites pre-existing
  files in default mode (source is authoritative). Only `--interactive` or
  `--less-interactive` prompts the user. The `create_` prefix provides a
  "only write if absent" semantic - analogous to vaultspec's scaffold step.

- **Three-way merge**: when both source and destination diverge from
  last-written, chezmoi opens a merge tool with all three versions.

**Relevance to vaultspec**: The three-state model (source / last-synced /
actual) is the right foundation. vaultspec already has snapshots
(`_snapshots/`) for builtins but doesn't use them for drift detection
during sync. The `doctor` pattern validates the independent signal
collector approach.

### Terraform - plan/apply with state file versioning

Terraform separates state into three representations: **desired**
(HCL config), **recorded** (state file), and **actual** (provider API).
Every `terraform plan` computes two diffs simultaneously: drift
(recorded vs actual) and config diff (actual vs desired).

Key patterns:

- **Resource lifecycle states** are minimal: `ObjectReady` (R),
  `ObjectTainted` (T), `ObjectPlanned` (P). Complexity lives in the
  *plan actions* (Create/Update/Delete/Replace/Forget) with separate
  *reason codes* explaining why.

- **State file carries metadata**: `serial` (monotonic counter for
  concurrent write detection), `lineage` (UUID for corruption detection),
  per-resource `schema_version` for migration.

- **Refresh runs in-memory** before every plan. State file is never
  written until the user approves `apply`. This is the diagnosis/resolution
  separation.

- **Import of pre-existing resources** requires explicit action
  (`terraform import`). One-to-one binding enforced. No silent adoption.

- **Plan/apply phase boundary** is strict: plan produces serializable
  `Change` objects with Before/After values. Apply builds a separate
  execution graph. Partial failure records progress rather than rolling
  back.

**Relevance to vaultspec**: The plan/apply separation maps directly to
the diagnosis/resolution architecture. Terraform's approach to reason
codes (not just actions but *why* each action is needed) should be adopted.
The `serial` + `lineage` pattern is applicable to manifest versioning.

### Ansible - fact gathering and desired state modules

Ansible uses independent `BaseFactCollector` classes that each return a
dict. An orchestrator runs them sequentially, passing accumulated results
so later collectors can reference earlier facts. Exception isolation
prevents one failure from halting collection.

Key patterns:

- **`state` parameter describes desired state**, not action:
  `present`/`absent` is universal. Domain modules extend with specialized
  states (`latest`, `started`/`stopped`, `file`/`directory`/`link`).
  The resolver infers the action from the gap between actual and desired.

- **Detect-compare-apply** is the universal module pattern: build `got`
  (actual) and `wanted` (desired), compare, exit early if no diff or in
  `check_mode`, otherwise apply.

- **`changed` boolean accumulation**: each sub-check sets
  `changed |= ...`. The final `changed` flag is the sole mechanism for
  reporting whether work was done. Simple and reliable.

- **`blockinfile` module** for managed blocks in user-owned files (see
  gitignore section below).

**Relevance to vaultspec**: The fact-collector pattern validates the
signal-collector architecture. Ansible's `state: present/absent`
vocabulary should inform how the resolver decides what to do. The
`changed` accumulator pattern is useful for sync reporting.

### uv - lock file vs environment drift

uv's `sync` command follows a desired-vs-actual diff model:

- Reads lockfile into a `Resolution` (desired state)
- Reads `SitePackages::from_environment()` (actual state)
- Compares via `RequirementSatisfaction::check()` checking: version,
  platform tags, hashes, URLs/paths
- Generates a `Plan` with four buckets: `cached`, `remote`, `reinstalls`,
  `extraneous`

**Relevance to vaultspec**: The four-bucket model (cached = skip, remote =
add, reinstalls = update, extraneous = prune) maps to sync result
accounting. uv trusts the lockfile and only computes the delta - this is
the right model for vaultspec's sync (trust `.vaultspec/` source, compute
delta to provider destinations).

### GNU Stow - stateless filesystem inspection with plan/execute

Stow stores **no database or manifest** between runs. All state is derived
from filesystem inspection at runtime: "there's no danger of mangling
directories when file hierarchies don't match the database."

Key patterns:

- **Two-phase algorithm**: Phase 1 (`plan_stow`/`plan_unstow`) traverses
  the tree building a task list. Conflicts are accumulated without
  modifying the filesystem. Phase 2 (`process_tasks`) only runs if zero
  conflicts were found.

- **Ownership detection** via path resolution: given a symlink, resolves
  its target and checks if it points into a known stow directory. Purely
  path-based, no registry.

- **Fold/unfold tree optimization**: a directory can be folded into a
  single symlink iff ALL children point into the same parent. When a
  second package needs the same directory, the symlink is "unfolded" into
  a real directory with symlinks from both packages.

- **Conflict types**: target exists and is not a symlink (blocks stowing),
  target is a symlink owned by a different package, type mismatch
  (directory vs file).

**Relevance to vaultspec**: The conflict-accumulation-before-execution
pattern is directly applicable. vaultspec should detect all conflicts
before making any filesystem changes. The fold/unfold model has parallels
to shared directories (`.agents/` shared by gemini, antigravity, codex).

### pre-commit - hash-based ownership detection

pre-commit detects whether a hook file is "ours" by searching for a
`CURRENT_HASH` or any of 5 `PRIOR_HASHES` in the file content. This
yields three states: not installed, installed (ours), foreign/unknown.

Key patterns:

- **Hash-based ownership**: embed identity markers in managed files to
  detect ownership without a manifest
- **Atomic operations**: temp file + `os.replace()` for writes; temp
  directories with cleanup-on-failure for clones
- **Version drift**: simple string inequality (`old.rev != new.rev`)

**Relevance to vaultspec**: The hash/marker ownership concept could
complement the manifest for detecting whether files in provider dirs were
created by vaultspec or by the user. The `AUTO-GENERATED` header already
in `types.py` serves a similar purpose but isn't used for detection.

## Observed signal dimensions

Analysis of the filesystem and manifest yields these independent signal
axes that compose into the full state space:

### Axis 1: framework presence

| Signal                                           | Detection                |
| ------------------------------------------------ | ------------------------ |
| `.vaultspec/` missing                            | Not installed            |
| `.vaultspec/` exists, no `providers.json`        | Corrupted or mid-install |
| `.vaultspec/` exists, `providers.json` malformed | Corrupted manifest       |
| `.vaultspec/` exists, `providers.json` valid     | Framework present        |

### Axis 2: provider directory state (per provider)

| Signal                                      | Detection                          |
| ------------------------------------------- | ---------------------------------- |
| Directory missing                           | Not scaffolded                     |
| Directory exists, empty                     | Scaffolded but never synced        |
| Directory exists, partial files             | Incomplete sync or manual deletion |
| Directory exists, all expected files        | Fully synced                       |
| Directory exists, extra non-vaultspec files | User content mixed in              |

### Axis 3: manifest-filesystem coherence

| Signal                                      | Detection                |
| ------------------------------------------- | ------------------------ |
| Provider in manifest, directory exists      | Coherent                 |
| Provider in manifest, directory missing     | Orphaned manifest entry  |
| Provider not in manifest, directory exists  | Untracked directory      |
| Provider not in manifest, directory missing | Coherent (not installed) |

### Axis 4: content integrity (per synced file)

Mirrors chezmoi's two-column status model:

| Signal                                | Detection | chezmoi analogy |
| ------------------------------------- | --------- | --------------- |
| File matches source transform         | Clean     | (two spaces)    |
| File differs from source transform    | Diverged  | `M` or `MM`     |
| File exists at destination, no source | Stale     | needs `D`       |
| Source exists, no destination file    | Missing   | `A`             |

### Axis 5: builtin version state

| Signal                            | Detection                               |
| --------------------------------- | --------------------------------------- |
| Builtins match snapshots          | Current                                 |
| Builtins differ from snapshots    | Modified by user                        |
| Builtins missing, snapshots exist | Deleted builtins                        |
| No snapshots directory            | Never snapshotted (pre-version install) |

### Axis 6: root config and MCP state

| Signal                                                        | Detection                   |
| ------------------------------------------------------------- | --------------------------- |
| `CLAUDE.md` / `GEMINI.md` / `AGENTS.md` present + well-formed | OK                          |
| Config file missing but provider installed                    | Config gap                  |
| `.mcp.json` missing                                           | MCP not configured          |
| `.mcp.json` present, missing vaultspec-core entry             | Partial MCP                 |
| `.mcp.json` present, has extra entries                        | User MCP content (preserve) |

### Axis 7: gitignore state (new requirement)

| Signal                                             | Detection                        |
| -------------------------------------------------- | -------------------------------- |
| `.gitignore` missing                               | No gitignore management possible |
| `.gitignore` exists, no vaultspec entries          | Managed dirs not ignored         |
| `.gitignore` exists, partial vaultspec entries     | Incomplete coverage              |
| `.gitignore` exists, all required entries present  | Fully covered                    |
| `.gitignore` has user entries near vaultspec block | Must preserve                    |

## Design approach: signal-based matrix resolver

Rather than enumerating every combination of the above axes as discrete
enum members (combinatorially explosive), the design uses a composable
signal collector that feeds into a resolver. This is validated by prior
art from all six tools studied.

### Pattern synthesis from prior art

| Pattern                     | Source tool         | Application in vaultspec                     |
| --------------------------- | ------------------- | -------------------------------------------- |
| Three-state comparison      | chezmoi             | Source / last-synced / actual per file       |
| Plan/apply separation       | Terraform, Stow     | Diagnosis produces plan, executor applies    |
| Independent fact collectors | Ansible             | One collector per signal axis                |
| Reason codes on actions     | Terraform           | Not just "update" but "why update"           |
| `state: present/absent`     | Ansible             | Desired state drives action inference        |
| Four-bucket diff            | uv                  | cached/remote/reinstall/extraneous           |
| Conflict accumulation       | Stow                | Detect all problems before any mutation      |
| Hash-based ownership        | pre-commit          | Detect managed vs user files via markers     |
| Managed block markers       | Ansible blockinfile | For gitignore management                     |
| Serial + lineage            | Terraform           | Manifest versioning for corruption detection |

### Architecture

**Layer 1 - Signal collectors** (pure functions, no side effects):

Each collector inspects one axis and returns a typed signal value.
Collectors are independent and can run in parallel. Modeled after
Ansible's `BaseFactCollector` pattern with exception isolation.

```
collect_framework_presence(target) -> FrameworkSignal
collect_provider_dir_state(target, tool) -> ProviderDirSignal
collect_manifest_coherence(target) -> ManifestCoherenceReport
collect_content_integrity(target, tool) -> ContentIntegrityReport
collect_builtin_version_state(target) -> BuiltinVersionSignal
collect_config_state(target, tool) -> ConfigSignal
collect_gitignore_state(target) -> GitignoreSignal
```

**Layer 2 - Workspace diagnosis** (aggregation):

Combines all signals into a `WorkspaceDiagnosis` dataclass. This is a
fact-only layer - no decisions, no actions. Analogous to Terraform's
in-memory refresh step that runs before every plan.

```python
@dataclass
class WorkspaceDiagnosis:
    framework: FrameworkSignal
    providers: dict[Tool, ProviderDiagnosis]
    manifest_coherence: ManifestCoherenceReport
    builtin_version: BuiltinVersionSignal
    gitignore: GitignoreSignal
```

**Layer 3 - Resolution engine** (decision logic):

Takes a `WorkspaceDiagnosis` and a requested action (install, sync,
uninstall, upgrade) and produces either:

- A `ResolutionPlan` with ordered remediation steps (each carrying a
  reason code, following Terraform's pattern), or
- A `ResolutionError` with a clear diagnostic message

Adopts Stow's conflict-accumulation pattern: all conflicts detected
before any filesystem mutation. Adopts Ansible's `state: present/absent`
vocabulary for expressing desired state.

**Layer 4 - Remediation executor** (side effects):

Executes `ResolutionPlan` steps in order. Adopts Terraform's approach
of recording progress rather than rolling back on partial failure.
Uses pre-commit's atomic write pattern (temp file + `os.replace()`).

### Signal types as enums

The individual signal values should be enums, but the combinations should
not. This keeps the enum space manageable:

```python
class FrameworkSignal(StrEnum):
    MISSING = "missing"
    CORRUPTED = "corrupted"
    PRESENT = "present"

class ProviderDirSignal(StrEnum):
    MISSING = "missing"
    EMPTY = "empty"
    PARTIAL = "partial"
    COMPLETE = "complete"
    MIXED = "mixed"  # has non-vaultspec content

class ManifestEntrySignal(StrEnum):
    COHERENT = "coherent"
    ORPHANED = "orphaned"        # in manifest, dir missing
    UNTRACKED = "untracked"      # dir exists, not in manifest
    NOT_INSTALLED = "not_installed"

class ContentSignal(StrEnum):
    CLEAN = "clean"
    DIVERGED = "diverged"
    STALE = "stale"
    MISSING = "missing"

class BuiltinVersionSignal(StrEnum):
    CURRENT = "current"
    MODIFIED = "modified"
    DELETED = "deleted"
    NO_SNAPSHOTS = "no_snapshots"

class GitignoreSignal(StrEnum):
    NO_FILE = "no_file"
    NO_ENTRIES = "no_entries"
    PARTIAL = "partial"
    COMPLETE = "complete"
```

### Content ownership detection

Following pre-commit's hash-based ownership and chezmoi's metadata
encoding, vaultspec should formalize file ownership detection:

- The existing `AUTO-GENERATED by cli.py config sync` header in root
  configs should be used as an ownership marker during diagnosis
- Synced rule/skill/agent files should carry a frontmatter marker (e.g.
  `vaultspec_managed: true`) to distinguish managed from user-authored
  files
- Files without ownership markers in provider directories are classified
  as user content (MIXED signal)

## Gitignore management requirements

### Prior art: Ansible blockinfile

The Ansible `blockinfile` module is the gold standard for managed blocks
in user-owned files. Its algorithm:

- Find `marker_begin` and `marker_end` lines by linear scan
- If both markers found: replace everything between them (inclusive)
- If neither found: insert at position determined by
  `insertafter`/`insertbefore` regex (default: EOF)
- If removing (`state=absent`): delete the entire marker range
- Supports multiple named blocks via unique markers
- Uses `{mark}` placeholder in marker template

Conda uses chevron-style markers (`>>>` / `<<<`) which are more visually
distinctive. SDKMAN uses only a begin marker (fragile anti-pattern).

### Recommended approach

Adopt Ansible's marker pattern adapted for gitignore syntax:

```gitignore
# >>> vaultspec-managed (do not edit this block) >>>
.vaultspec/_snapshots/
# <<< vaultspec-managed <<<
```

Using conda's chevron style for visual distinctiveness in gitignore files
where `#` comments are common.

Implementation rules:

- Only modify content between chevron markers
- Never touch content outside the managed block
- Create the block on `install` if `.gitignore` exists
- Remove the block on `uninstall --force`
- `sync` verifies block is present and correct (adds if missing, updates
  if stale)
- If user deletes the block, respect that decision (track in manifest
  whether block was ever created, don't recreate if user removed it)

### Separate ADR needed

Gitignore management warrants its own ADR to resolve:

- What exactly gets gitignored (opt-in vs opt-out per provider)
- Whether `vaultspec sync` should maintain gitignore
- How to handle repos without `.gitignore` (create or skip)
- Interaction with `.git/info/exclude`
- Whether provider-specific ignores should differ

## Installation versioning

### Prior art: Terraform state versioning

Terraform's state file carries: `serial` (monotonic counter incremented
on every write, detects concurrent modifications), `lineage` (UUID
generated on first create, detects corruption/replacement), and
per-resource `schema_version` (enables migration when resource schema
changes).

### Proposed manifest extension

```json
{
  "version": "2.0",
  "vaultspec_version": "0.1.4",
  "installed_at": "2026-03-27T10:00:00Z",
  "layout_version": 1,
  "serial": 1,
  "lineage": "a1b2c3d4-...",
  "installed": ["claude", "gemini"],
  "provider_state": {
    "claude": {
      "installed_at": "2026-03-27T10:00:00Z",
      "last_synced": "2026-03-27T10:05:00Z"
    }
  },
  "gitignore_managed": true
}
```

Fields adopted from Terraform:

- `serial`: incremented on every manifest write, detects concurrent edits
- `lineage`: UUID generated at first install, detects manifest replacement
- `layout_version`: integer for filesystem layout migration
- `vaultspec_version`: the version of vaultspec-core that last wrote

The `gitignore_managed` flag tracks whether the managed block was ever
created, to respect user removal decisions.

## Test matrix requirements

The test suite needs parametrized fixtures that can produce each signal
combination. Key scenarios:

- **Vanilla install** - clean directory, no pre-existing content
- **Partial install** - `.vaultspec/` exists, some providers missing
- **Corrupted manifest** - malformed JSON in `providers.json`
- **Orphaned directories** - provider dirs exist but not in manifest
- **Stale content** - synced files that no longer match sources
- **Mixed content** - provider dirs with both vaultspec and user files
- **Pre-existing provider config** - `.claude/` exists before install
  with user rules
- **Empty directories** - scaffolded but never synced
- **Old version install** - manifest from older vaultspec version
- **Missing builtins** - `.vaultspec/rules/` partially deleted
- **No gitignore** - git repo with no `.gitignore`
- **Partial gitignore** - `.gitignore` exists but missing vaultspec entries

Following Stow's approach, the test suite should verify that **no
filesystem mutations occur when conflicts are detected** (plan phase
completes, execute phase is gated on zero conflicts).

## Risk assessment

| Risk                                   | Mitigation                                                             | Prior art                   |
| -------------------------------------- | ---------------------------------------------------------------------- | --------------------------- |
| Over-engineering the resolver          | Start with 3-4 most common failure modes, extend incrementally         | Stow's simplicity           |
| Breaking existing install flows        | Resolver wraps existing commands, same external behavior               | Terraform's backward compat |
| Content ownership false positives      | Use explicit markers, not heuristics                                   | pre-commit hashes           |
| Gitignore management conflicts         | Managed block pattern, never touch outside block                       | Ansible blockinfile         |
| Manifest corruption                    | Serial + lineage detection, fail-closed                                | Terraform state locking     |
| Performance overhead of full diagnosis | Lazy collection - only run collectors needed for the requested command | Ansible fact caching        |

## Findings summary

- The signal-based architecture is validated by all six prior art tools
- chezmoi's three-state model (source/last-written/actual) is the closest
  analog and should be adopted for content integrity checking
- Terraform's plan/apply separation and reason codes should structure
  the resolver
- Ansible's fact collector pattern and blockinfile module provide direct
  implementation blueprints
- Stow's conflict-accumulation-before-execution is a critical safety
  pattern
- pre-commit's hash-based ownership complements manifest-based tracking
- uv's four-bucket diff model maps cleanly to sync result accounting
- Gitignore management should be a separate ADR using Ansible's
  blockinfile pattern with conda's chevron markers
- Installation versioning should adopt Terraform's serial + lineage model
