---
tags:
  - '#adr'
  - '#provisioning-tests'
date: '2026-09-05'
modified: '2026-09-05'
body_schema: 'body-v2'
body_hash: 'sha256:6fb88c46604add70c069bd5a51eebb6399c3c0f9542890a3c5f16ecd5bc6120d'
related:
  - '[[2026-09-05-provisioning-tests-research]]'
---

# `provisioning-tests` adr: `Provisioning tests: marker, location, and the hosted Windows leg` | (**status:** `accepted`)

## Problem Statement

`vaultspec-rag` has landed tests that drive real `uv` against real environments to prove
provisioning behaviour under hostile conditions, and the decision governing them was written
as one convention for both repositories. rag's half is implemented; Core's half has no
record, and an ADR in rag cannot govern this repository. Without one, the first
environment-mutating test written here picks its own marker and location, and the convention
silently becomes two conventions.

The decision is needed now rather than when the need arrives, because the cost of deciding
late is a migration rather than a choice.

## Considerations

- Core and rag carry comparable responsibility: both install themselves, both ship a CLI
  plus an MCP server, both mutate environments. That symmetry is the argument for one
  convention rather than two.
- Core has no real-`uv` provisioning tests today; see `2026-09-05-provisioning-tests-research`.
  This is a convention adopted before the need, not a migration of existing tests.
- Core already runs real-subprocess and real-OS-lock tests under `unit`
  (`src/vaultspec_core/core/tests/test_advisory_lock.py`), and rag independently does the
  equivalent. Two repositories arriving at the same marker without coordinating is evidence
  about what the marker means.
- Core already gates pull requests on hosted Windows (`.github/workflows/ci.yml`,
  `broad-tests` and `windows-vault-repair`), so the CI half of the convention costs no new
  lane here.
- Core states location-by-marker for its own `repo` marker at `dev/toolchain.py:538-546`.
- The behaviours such tests must encode are narrow and measured rather than assumed; the
  destructive case in particular is one specific failure, not a general hazard
  (`2026-09-05-provisioning-tests-research`).

## Considered options

- **Marker `unit`, beside the code, hosted Windows at PR time (chosen).** Matches what both
  repositories already do for real-subprocess tests, and needs no new CI lane in Core.
  Costs: `unit` carries tests that spawn processes and touch the filesystem, which surprises
  a reader who expects `unit` to mean in-memory.
- **A dedicated `provisioning` marker (rejected).** Honest about what the tests do, and
  selectable in isolation. Rejected because it diverges from rag for no behavioural gain,
  and because the thing that makes a test slow is hardware and credentials, not spawning a
  process - so the split would not buy a faster default lane.
- **An `integration/` directory, selected by path (rejected).** rag's current shape. Rejected
  for Core because Core selects by marker rather than directory everywhere else, and
  adopting a second selection mechanism for one class of test is the divergence this ADR
  exists to prevent.
- **Self-hosted Windows leg (rejected).** rag needs one because its Windows jobs are
  excluded from the pull-request lane so a fork's code never reaches the fleet. Core's
  Windows jobs are hosted and already gate PRs, so a self-hosted leg would add fleet
  exposure and buy nothing.

## Constraints

- The governing record in rag, `2026-09-04-cuda-provisioning-adr` (decision D7), was on an
  unmerged branch when this was written, so it is context rather than authority; this record
  is the durable half for Core until it lands. Should rag's land differently, this record is
  amended rather than superseded.
- `uv` behaviour is a moving target: everything grounding this decision was measured against
  `uv 0.12.8` and may need re-measuring on a major bump
  (`2026-09-05-provisioning-tests-research`).
- Hosted `windows-latest` runners are where the destructive case reproduces; the convention
  therefore depends on that leg continuing to gate pull requests.

## Implementation

Tests exercising `install`, `uninstall`, or `sync` against a real environment rather than a
mocked one carry the `unit` marker and sit beside the code under test, selected by marker
rather than by directory. They are swept into the existing hosted `windows-latest` leg and
gate a merge like every other test.

Each such test redirects `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR` and `UV_CACHE_DIR` into a sandbox
so no live installation is touched, and serves any stand-in distribution over loopback HTTP
rather than `file://`. Both constraints follow from measured `uv` behaviour rather than
caution; the reasons are in `2026-09-05-provisioning-tests-research`.

Nothing is added to Core's dependencies and nothing is imported from rag: this is a shared
convention, not shared code.

## Rationale

The marker choice turns on one observation: both repositories already run real-subprocess,
real-OS-lock tests under `unit`, independently and without coordinating. That convergence is
the argument. A marker earns its own lane when it needs hardware or credentials, and these
tests need neither - they need a sandboxed environment directory and a loopback port.

Location-by-marker rather than by directory is the same reasoning Core already applies to its
`repo` marker, so the alternative would introduce a second selection mechanism for a single
class of test.

The hosted Windows leg is the one part where Core and rag genuinely differ, and recording why
matters: rag's self-hosted Windows jobs are excluded from the pull-request lane, so rag had to
add a hosted leg. Core's already gate PRs. Reading the two decisions side by side without that
asymmetry written down would suggest one repository is doing it wrong.

## Consequences

Core gains a stated home for environment-mutating tests before it has any, so the first one
written does not set the precedent by accident. The two repositories stay legible to a reader
who works across both.

The honest cost is that `unit` now spans in-memory tests and tests that spawn `uv` and write
to disk. A reader who assumes `unit` means fast and pure will be wrong, and the marker's
meaning is now carried by convention rather than by its name. Splitting later means moving
tests and updating CI selectors in two repositories at once.

This also binds Core to hosted Windows continuing to gate pull requests. If that lane is ever
narrowed for cost, the convention loses the platform where its most interesting failure - the
non-atomic forced install - actually reproduces, and this record needs revisiting rather than
quietly eroding.
