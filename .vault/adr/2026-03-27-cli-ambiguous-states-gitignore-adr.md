---
tags:
  - '#adr'
  - '#cli-ambiguous-states'
date: '2026-03-27'
related:
  - '[[2026-03-27-cli-ambiguous-states-research]]'
  - '[[2026-03-27-cli-ambiguous-states-prior-art-research]]'
  - '[[2026-03-27-cli-ambiguous-states-resolver-adr]]'
---

# `cli-ambiguous-states` adr: gitignore managed block support | (**status:** `accepted`)

## Problem Statement

The CLI never checks whether provider-managed paths or internal
vaultspec paths are gitignored. Users who commit generated files
may encounter noisy diffs, merge conflicts on synced content, or
accidentally push internal state (snapshots). Conversely, users
who manually add gitignore entries get them silently clobbered
or face drift when vaultspec adds new managed paths.

The CLI needs a mechanism to manage a subset of `.gitignore` entries
without interfering with user-authored entries.

## Considerations

- **Ansible blockinfile** is the gold standard for managed blocks in
  user-owned files. Algorithm: linear scan for begin/end markers,
  replace range (inclusive), or insert at configurable position.
  Supports multiple named blocks via unique markers. Proven over 10+
  years across millions of deployments.

- **Conda conda init** uses chevron-style markers (`>>>` / `<<<`) which
  are more visually distinctive in files where `#` comments are common
  (shell configs, gitignore). Regex-based find-and-replace with a
  placeholder swap technique to prevent regex substitution bugs.

- **Nix installer** uses simple `# Nix` / `# End Nix` bookends. Known
  fragile - macOS system updates frequently clobber these.

- **SDKMAN** uses only a begin marker with no end marker. Relies on EOF
  positioning. Documented anti-pattern.

- The `blockinfile` Python package on PyPI is a direct port of Ansible's
  module (GPLv3+). License is incompatible with this project - must
  reimplement, but the algorithm is well-documented.

## Constraints

- Must never modify content outside the managed block markers.

- Must preserve all user-authored `.gitignore` entries exactly as they
  are, regardless of position relative to the managed block.

- Must handle: file missing, file empty, file with no block, file with
  existing block, file with stale block content, file with orphaned
  single marker.

- Must not create `.gitignore` if it doesn't exist. Users who don't use
  `.gitignore` have made a deliberate choice.

- Must respect user removal of the managed block: if the user deletes
  the block, do not silently recreate it on next sync. Track opt-out
  state in manifest via `gitignore_managed` flag.

- The managed block content must be deterministic and idempotent:
  running the same operation twice produces the same result with no
  diff.

- Must handle Windows CRLF line endings and trailing whitespace on
  marker lines. Must preserve the file's existing line-ending
  convention.

## Implementation

### Marker format

Adopt conda's chevron style for visual distinctiveness:

```gitignore
# >>> vaultspec-managed (do not edit this block) >>>
.vaultspec/_snapshots/
# <<< vaultspec-managed <<<
```

The chevron markers are more visually distinctive than `BEGIN`/`END`
in gitignore files where `#` comment lines are common. The parenthetical
"do not edit this block" is a human-readable warning, not parsed.

### Managed entries

Default entries added to the block on install:

```
.vaultspec/_snapshots/
```

Only internal state directories that are never user-facing. The block
is intentionally minimal. Provider output directories (`.claude/`,
`.gemini/`, etc.) and root configs (`CLAUDE.md`, etc.) are NOT
gitignored by default - they are user-facing and many workflows
benefit from tracking them.

Entries may grow in future versions as new internal paths are added.
The block is updated on `sync` and `install --upgrade` to ensure new
entries are picked up.

### Algorithm (new module: `core/gitignore.py`)

```python
MARKER_BEGIN = "# >>> vaultspec-managed (do not edit this block) >>>"
MARKER_END = "# <<< vaultspec-managed <<<"

def ensure_gitignore_block(
    target: Path,
    entries: list[str],
    *,
    state: str = "present",   # "present" or "absent"
) -> bool:
    """Manage the vaultspec block in .gitignore.

    Returns True if the file was modified, False if no change needed.
    """
```

**Line ending handling**: read file content with `Path.read_text()`.
Split using `str.splitlines()` (handles `\r\n`, `\r`, `\n`
transparently). Detect the file's dominant line ending by inspecting
the raw bytes. Write back using the detected line ending. Strip
trailing whitespace from each line before marker comparison.

**state=present** algorithm (following Ansible blockinfile):

- Read `.gitignore` content. If file doesn't exist, return False (no-op).
- Split into lines. Detect line ending convention.
- Scan for `MARKER_BEGIN` and `MARKER_END` line indices, comparing
  after stripping trailing whitespace.
- Build the new block: `[MARKER_BEGIN] + entries + [MARKER_END]`.
- If both markers found: replace lines from begin to end (inclusive)
  with new block. Compare result to original - if identical, return
  False (idempotent no-op).
- If neither marker found: strip trailing blank lines from file, add
  one blank separator line, then append new block. Ensure file ends
  with a newline.
- If only one marker found (corrupted state): remove the orphaned
  marker line, then proceed as "neither found" (append fresh block).
  Emit a warning about the repair.
- Write result back using the existing `atomic_write` helper from
  `core/helpers.py` (handles Windows `os.replace()` fallback).

**state=absent** algorithm:

- Read `.gitignore` content.
- If both markers found: remove lines from begin to end (inclusive).
  Collapse any resulting double blank lines into a single blank line.
- If only one marker found: remove the orphaned marker line.
- Write result back via `atomic_write`.

### CLI integration

**`vaultspec-core install`**: after scaffolding and sync, call
`ensure_gitignore_block(target, DEFAULT_ENTRIES, state="present")`.
Set `gitignore_managed: true` in manifest on success.

**`vaultspec-core sync`**: if `gitignore_managed` is true in manifest,
call `ensure_gitignore_block()` to update the block with current
entries. If the block was removed by the user (markers not found but
`gitignore_managed` was true), set `gitignore_managed: false` in
manifest and emit a warning. Do not recreate.

**`vaultspec-core install --upgrade`**: if `gitignore_managed` is true,
update the block with current entries (may add new entries from newer
vaultspec version). If `gitignore_managed` is false (user opted out),
do not touch `.gitignore`.

**`vaultspec-core uninstall --force`**: call
`ensure_gitignore_block(target, [], state="absent")`.

**`vaultspec-core doctor`**: report gitignore signal as part of
workspace diagnosis. The `collect_gitignore_state()` collector
checks for marker presence and entry completeness.

**Re-opt-in path**: users who previously opted out (removed the block,
causing `gitignore_managed: false`) can re-enable by running
`vaultspec-core install --upgrade --force`. The `--force` flag
resets `gitignore_managed` to true and recreates the block.

### Signal integration with resolver ADR

The `GitignoreSignal` enum from the resolver ADR maps to this
implementation:

- `NO_FILE`: `.gitignore` doesn't exist. No action taken.
- `NO_ENTRIES`: `.gitignore` exists, no managed block found. Install
  should add. Sync should add only if `gitignore_managed` is true.
- `PARTIAL`: managed block exists but entries are stale (subset of
  expected). Sync should update.
- `COMPLETE`: managed block exists with all expected entries. No-op.
- `CORRUPTED`: only one marker found (orphaned). Resolver emits a
  `REPAIR_GITIGNORE` step to fix the corruption before proceeding.

### Interaction with `.git/info/exclude`

Out of scope for this ADR. `.git/info/exclude` is a local-only
mechanism that doesn't propagate to collaborators. If a user prefers
this approach, they can opt out of gitignore management and handle
entries manually. Future work could add a `--gitignore-target` flag
to `install` to choose between `.gitignore` and `.git/info/exclude`.

## Rationale

- **Conda chevron markers over Ansible BEGIN/END**: both work, but
  chevrons are more visually distinctive in gitignore files where `#`
  comments are the norm. The conda pattern is proven in a major tool.

- **Minimal default entries**: only internal state (`.vaultspec/_snapshots/`)
  is gitignored by default. Provider output directories are user-facing
  content that many workflows track in git. Opinionated defaults can be
  extended later; it's harder to un-ignore files that users have already
  committed.

- **Respect user removal**: tracking `gitignore_managed` in the manifest
  prevents the frustrating "tool keeps recreating what I deleted"
  anti-pattern. The user is always in control. Re-opt-in is available
  via `install --upgrade --force`.

- **No `.gitignore` creation**: if the file doesn't exist, the user has
  made a choice (or isn't using git). Creating the file would be
  presumptuous.

- **Reuse `atomic_write`**: the existing helper in `core/helpers.py`
  already handles the Windows `os.replace()` edge case with a fallback
  to `copyfile + unlink`. No need to reimplement.

- **Remove orphaned markers**: leaving dead markers in the file is a
  time bomb for future runs and confuses users. Clean removal with a
  warning is the safer choice.

- **Ansible's algorithm, reimplemented**: the `blockinfile` PyPI package
  is GPLv3+ (incompatible). The algorithm itself is simple (linear scan

  - splice) and well-documented enough to reimplement cleanly.

## Consequences

- **New module**: `core/gitignore.py` (~100-150 lines). Small, focused.

- **Manifest dependency**: requires the `gitignore_managed` field from
  manifest v2.0 (defined in the resolver ADR). Implementation order:
  manifest v2.0 first, then gitignore module, then resolver integration.

- **Test surface**: needs fixtures for: no `.gitignore`, empty file,
  file with no block, file with existing block, file with stale block,
  file with orphaned begin marker, file with orphaned end marker,
  file with user content above/below block, user removal of block,
  CRLF line endings, BOM-prefixed file, file ending without newline,
  file with multiple trailing blank lines.

- **No provider-specific ignores**: all providers share the same managed
  block. If provider-specific ignores become necessary, the marker
  format supports it (unique marker strings per provider, as Ansible
  supports) but this is deferred.

- **Future extensibility**: new entries can be added to the default list.
  Existing blocks are updated on next sync automatically.
