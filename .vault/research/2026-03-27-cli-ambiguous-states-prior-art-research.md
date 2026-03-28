---
tags:
  - '#research'
  - '#cli-ambiguous-states'
date: '2026-03-27'
related:
  - '[[2026-03-27-cli-ambiguous-states-research]]'
---

# `cli-ambiguous-states` research: prior art grounding

Detailed prior art analysis of how mature CLI tools handle filesystem
state detection, content management, drift reconciliation, and managed
blocks in user-owned files. Companion to the main research document.

## Findings

### chezmoi (dotfile manager)

**Architecture**: Three distinct states per managed entry - source state
(desired, stored in chezmoi repo), destination state (actual on disk),
and last-written state (persisted in BoltDB). Enables three-way drift
detection that distinguishes "user edited this" from "source changed".

**State types** from `internal/chezmoi/entrystate.go`:

- `EntryStateType`: `dir`, `file`, `symlink`, `remove`, `script`
- `EntryState` struct: `Type`, `Mode`, `ContentsSHA256`, `contents`, `overwrite`
- Nil `EntryState` is equivalent to `remove` (absent)
- `Equivalent()` method handles nil-as-absent convention

**Actual state detection** via `ActualStateEntry` interface with concrete
types: `ActualStateAbsent` (lstat returns ErrNotExist), `ActualStateFile`
(regular file with perm + lazy contents), `ActualStateDir`, `ActualStateSymlink`.
Detection uses `system.Lstat()` dispatch on `fileInfo.Mode().Type()`.

**Status command** uses two-column output:

- Column 1: last-written vs actual (local edits since last apply)
- Column 2: actual vs desired (what apply would do)
- Codes: `A` (add), `M` (modify), `D` (delete), `R` (run), (space) (clean)
- Key combinations: `MM` = modified on both sides (conflict), `DA` =
  deleted locally but will be recreated, `A` = new in source

**Doctor command** from `internal/cmd/doctorcmd.go`:

- Check result enum: `omitted`, `failed`, `skipped`, `ok`, `info`,
  `warning`, `error`
- Checks: version, latest version (GitHub API), OS/arch, config file
  existence/validity, source dir exists, suspicious entries (unencrypted
  files that should be encrypted), dest dir exists, filesystem
  capabilities (hardlink, symlink), umask, binary checks for 20+ tools
- Each check is an independent function returning a `checkResult`

**Conflict resolution** via `defaultPreApplyFunc`:

- `targetDirty`: file modified since chezmoi last wrote it
- `targetPreExisting`: file exists but chezmoi has no record of writing it
- Default: silently overwrite pre-existing files (source is authoritative)
- `--interactive`: prompt for every file
- `--less-interactive`: prompt only for dirty or pre-existing files
- `--force`: skip all prompts

**Partial file management**: `create_` prefix (only write if absent) and
`modify_` prefix (script receives current contents on stdin, outputs new
contents). No marker-based block management.

### Terraform (infrastructure as code)

**State model**: Three representations - desired (HCL config), recorded
(state file), actual (provider API). `terraform plan` computes two diffs:
drift (recorded vs actual) and config diff (actual vs desired).

**Resource lifecycle states** from `internal/states/instance_object.go`:

- `ObjectReady` ('R') - fully operational
- `ObjectTainted` ('T') - needs recreation (manual taint or partial failure)
- `ObjectPlanned` ('P') - proposed but not yet created

The deposed/current dimension is structural (a slot in
`ResourceInstance`), not a status flag. Plan actions
(Create/Update/Delete/Replace/Forget) carry separate reason codes.

**State file versioning** from `internal/states/statefile/version4.go`:

- `serial`: monotonic counter incremented on every write
- `lineage`: UUID generated on first create
- Per-resource `schema_version` for migration
- `private` opaque blob for provider-specific data

**Refresh** runs in-memory before every plan. Provider API is queried for
each resource, compared against recorded state, updated in memory. State
file is never written until user approves `apply`.

**Import**: pre-existing resources require explicit `terraform import`.
One-to-one binding enforced. Config must exist. Post-import diffs expected
and must be reconciled.

**Plan/apply boundary**: strict phase separation. Plan builds dependency
graph, walks in parallel, produces serializable `Change` objects with
Before/After values. Apply builds separate execution graph from plan.
Partial failure records progress rather than rolling back.

### Ansible (configuration management)

**Fact gathering** via `BaseFactCollector` classes:

- Each collector returns a dict of facts
- Orchestrator runs sequentially, passing accumulated results
- Exception isolation prevents one failure from halting collection
- Collectors can be filtered by name or subset

**Module pattern** (detect-compare-apply):

- Build `got` (actual state) and `wanted` (desired state)
- Compare; exit early if no diff or in `check_mode`
- Apply changes if needed
- Report `changed` boolean

**State parameter vocabulary**:

- Universal: `present` / `absent`
- Package: `present` / `absent` / `latest`
- Service: `started` / `stopped` / `restarted` / `reloaded`
- File: `file` / `directory` / `link` / `hard` / `touch` / `absent`

The state describes **what should exist**, not what action to take. The
module infers the action from the gap between actual and desired.

**Idempotency** via boolean accumulation: `changed |= ...` across
sub-checks. Simple and reliable.

**File module** state detection: uses `os.lstat()` (not stat - avoids
following symlinks), classifies via `stat.S_ISLNK`/`S_ISDIR`/`st_nlink`,
dispatches to dedicated `ensure_*()` functions per target state.

### uv (Python package manager)

**Sync model** from `crates/uv-installer/src/plan.rs`:

- Read lockfile into `Resolution` (desired state)
- Read `SitePackages::from_environment()` (actual state)
- Compare via `RequirementSatisfaction::check()`: version, platform tags,
  hashes, URLs/paths, build configuration
- Generate `Plan` with four buckets: `cached`, `remote`, `reinstalls`,
  `extraneous`

uv trusts the lockfile and only computes the delta. No re-resolution
during sync. Pre-validation: Python version checked against lockfile
constraints, extras/dev-groups validated before install.

### GNU Stow (symlink farm manager)

**Stateless design**: stores no database or manifest. All state derived
from filesystem inspection at runtime.

**Two-phase algorithm**:

- Phase 1 (plan): `plan_stow()`/`plan_unstow()` traverse tree, build
  task list, accumulate conflicts. No filesystem modifications.
- Phase 2 (execute): `process_tasks()` only runs if zero conflicts.
  Tasks: create/remove links and dirs, move files.

**Fold/unfold tree optimization**:

- `foldable()`: directory can be folded into a single symlink iff ALL
  children are symlinks AND all point into the same parent in the same
  package
- Unfold: when a new package needs a directory that's currently a folded
  symlink, remove the symlink, create a real directory, recursively stow
  contents from BOTH packages
- Re-fold on unstow: after removing links, check if directory is now
  foldable again

**Ownership detection**: given a symlink, resolve its target, check if it
points into any known stow directory. Purely path-based.

**Conflict types**: target is plain file (blocks stowing), target is
symlink owned by different package, type mismatch (dir vs file), absolute
symlink (cannot unstow).

### pre-commit (git hook manager)

**Hash-based ownership**: hook file searched for `CURRENT_HASH` or any of
5 `PRIOR_HASHES`. Three states: not installed, installed (ours),
foreign/unknown.

**Persisted state**: SQLite database in `~/.cache/pre-commit/` with
`repos` table (URL, ref, local path) and `configs` table. Cloned repo
directories alongside.

**Atomic operations**: temp file + `os.replace()` for writes. Double-check
locking. Temp directories with cleanup-on-failure before DB record
insertion. Graceful degradation to read-only mode.

**Version drift**: simple string inequality `old.rev != new.rev` via
`git ls-remote`. No semantic versioning.

### Managed blocks in user-owned files

**Ansible blockinfile** (gold standard):

- Default marker: `# {mark} ANSIBLE MANAGED BLOCK` where `{mark}` is
  replaced with `BEGIN`/`END`
- Algorithm: linear scan for both markers, replace range (inclusive), or
  insert at `insertafter`/`insertbefore` position
- Multiple blocks: each needs a unique marker string
- Custom markers for different file formats: `<!-- {mark} -->` for HTML,
  `; {mark}` for INI, `// {mark}` for C-style
- Removal: `state=absent` deletes the entire marker range
- Idempotency: compares original vs result, no-op if identical

**Conda conda init**:

- Chevron markers: `# >>> conda initialize >>>` / `# <<< conda initialize <<<`
- Regex-based find and replace
- Uses placeholder string during substitution to prevent regex issues
- Shell-specific content generation (bash, zsh, PowerShell uses
  `#region`/`#endregion`)

**Nix installer**: simple `# Nix` / `# End Nix` bookends. Known fragile -
macOS system updates frequently clobber these.

**SDKMAN**: single begin marker, no end marker. Relies on being at EOF.
Fragile anti-pattern.

**Python library**: `blockinfile` on PyPI (GPLv3+) is a direct port of
Ansible's module to a standalone CLI/library.

### Pattern summary

| Pattern                                | Tools           | Maturity                 |
| -------------------------------------- | --------------- | ------------------------ |
| Three-state comparison                 | chezmoi         | Proven, 5+ years         |
| Plan/apply separation                  | Terraform, Stow | Industry standard        |
| Independent fact collectors            | Ansible         | 10+ years, battle-tested |
| Reason codes on actions                | Terraform       | Standard in IaC          |
| Hash-based ownership                   | pre-commit      | Proven for managed files |
| Managed block markers                  | Ansible, Conda  | Proven, multiple impls   |
| Serial + lineage versioning            | Terraform       | Industry standard        |
| Four-bucket diff                       | uv              | Modern, proven at scale  |
| Stateless filesystem inspection        | Stow            | 20+ years, simple        |
| Conflict accumulation before execution | Stow            | Safety critical pattern  |
