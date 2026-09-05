---
tags:
  - '#research'
  - '#provisioning-tests'
date: '2026-09-05'
modified: '2026-09-05'
body_schema: 'body-v2'
body_hash: 'sha256:46ea4cf2793a7504aeb0f05c3fdc1bb5fa07d46400a92b4a604faa612a7f8aa2'
related: []
---

# `provisioning-tests` research: `Real-uv provisioning behaviour under hostile conditions`

## Scope

What `uv` does to a tool environment under hostile conditions, measured so that a
provisioning test suite asserts observed behaviour rather than assumed behaviour. Gathered
against `uv 0.12.8` on Windows 11, in redirected `UV_TOOL_DIR` / `UV_TOOL_BIN_DIR` /
`UV_CACHE_DIR` sandboxes; no live installation was touched. Reported in issue #406, whose
sibling work lives in `vaultspec-rag`.

## Findings

**A forced tool install is not atomic.** `uv` removes the installed distributions before
writing replacements. A file it cannot remove stops it there, leaving the environment
unrunnable rather than unchanged. Observed: `error: failed to remove directory ...\Scripts: Access is denied`, with `site-packages` already gone and the receipt surviving
to describe an environment that no longer exists. A test that asserts "failed install
leaves the environment intact" would therefore be asserting something untrue on Windows.

**Two relations hold an environment, not one.** A process whose *image path* is inside the
tree, and a process whose *working directory* is inside the tree. The second blocks removal
even when its binary is entirely unrelated, fails with a different Windows error (32 rather
than 5), and left the directory emptier in testing. A check that looks only at image paths
reports such a machine clear.

**Resolve-stage failures are safe.** An unreachable wheel or a wrong interpreter tag fails
before `uv` replaces anything, leaving both the environment and the receipt intact. Only a
blocked removal is destructive. This is the boundary a test suite should encode: the
dangerous case is narrow and identifiable.

**`file://` is not receipt-faithful.** `uv` records a `file://` requirement under a `path`
key and an `http(s)` one under `url`. A test serving a stand-in wheel over `file://` passes
receipt-verification assertions without ever entering the branch production reads. Stand-ins
must be served over loopback HTTP.

**`uv` serialises concurrent tool installs** under a `.lock` in the tool directory, so no
client-side lock is needed for that case.

**`uv tool install` refuses a distribution with no console-script entry point**, which
constrains what a stand-in package must declare.

## Bearing on Core

Core has no real-`uv` provisioning tests today. A search across `src/vaultspec_core` and
`dev/` for `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR`, `UV_CACHE_DIR`, and `uv tool install` finds
only harness dispatch at `dev/runner.py:162` and the literal `"uv"` inside mock MCP config
in `src/vaultspec_core/core/tests/test_mcps.py`. So the findings above describe a class of
test Core does not yet have, gathered before the need rather than after a failure.

Two facts about Core's own suite bear on where such tests would live. Core already runs
real-subprocess and real-OS-lock tests under the `unit` marker:
`src/vaultspec_core/core/tests/test_advisory_lock.py` spawns a child process to hold a real
lock file. And Core already gates pull requests on hosted Windows, in the `broad-tests` and
`windows-vault-repair` jobs of `.github/workflows/ci.yml`.

## Sources

The governing record in `vaultspec-rag` is `2026-09-04-cuda-provisioning-adr` (decision D7).
It was on an unmerged branch when issue #406 was filed, so it is context rather than
authority, and issue #406 is the durable half until it lands.

- `uv 0.12.8` on Windows 11, in redirected `UV_TOOL_DIR` / `UV_TOOL_BIN_DIR` /
  `UV_CACHE_DIR` sandboxes.
- `src/vaultspec_core/core/tests/test_advisory_lock.py` - Core's existing real-subprocess,
  real-OS-lock tests under the `unit` marker.
- `.github/workflows/ci.yml` - the `broad-tests` and `windows-vault-repair` jobs that
  already gate pull requests on hosted Windows.
- `dev/toolchain.py:538-546` - Core's statement of location-by-marker for its `repo` marker.
- `dev/runner.py:162` and `src/vaultspec_core/core/tests/test_mcps.py` - the only two hits
  for `uv` tooling in Core today, both incidental.
