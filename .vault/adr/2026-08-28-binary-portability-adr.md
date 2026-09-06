---
tags:
  - "#adr"
  - "#binary-portability"
date: '2026-08-28'
related:
  - "[[2026-03-22-clci-release-adr]]"
  - "[[2026-08-28-binary-portability-research]]"
superseded_by: '2026-09-06-binary-bootstrapper-adr'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:5ad57613701c61a2e730bf42e8fff8685672d377deafbd28e4994a69eaab2eaa'
---

# `binary-portability` adr: `declare the binary platform contract and enforce it at build time` | (**status:** `superseded`)

## Problem Statement

The release publishes standalone binaries whose platform contract is nowhere
declared. `2026-03-22-clci-release-adr` chose PyApp and named four target
triples, but settled nothing about what a target triple entitles a user to
expect: which OS versions the artifact loads on, whether it runs without a
network, or what must be true of it before it becomes a release asset.

Absent a declared contract, each artifact inherits whatever its build machine
supplies. `2026-08-28-binary-portability-research` shows what that has produced
in `vaultspec-core-v0.1.60`, and - because the inherited floor moves whenever a
runner is upgraded - shows that the failure recurs on its own rather than being
a one-time defect to repair. A decision is needed now because the repair and
the recurrence have different remedies, and only the second one holds.

## Considerations

- The Linux artifact's floor tracks the build host and nothing pins it
  (`2026-08-28-binary-portability-research`).
- Pinning the floor is free at runtime: the pidfd fast path survives a
  2.28-baseline build (`2026-08-28-binary-portability-research`).
- The pipeline executes no artifact it publishes, so any equivalent regression
  on any target is equally invisible
  (`2026-08-28-binary-portability-research`).
- One target - Intel macOS - is cross-built and no host exists that can run it.
- The binaries embed an interpreter but resolve the project from PyPI at first
  launch, so "standalone" is currently false on every target
  (`2026-08-28-binary-portability-research`).
- The build fleet is self-hosted and shared; adding per-target verification
  costs fleet time on every release.

## Considered options

**Declare a floor and assert it, without executing artifacts.** Pin the Linux
build to an old-glibc container and add a symbol-table check. Cheap and fixes
the known defect, but asserts only the property that already failed - it is the
repair, not the remedy, and the next inherited property to drift is unguarded.

**Execute every artifact on a matching host, without declaring a floor.**
A smoke run catches loader failures on the platforms the fleet happens to have.
It cannot speak for platforms with no runner, which is exactly the population
that broke: the fleet's Linux host is newer than every distribution the
regression affected, so a smoke run there would have passed.

**Declare the contract, assert it statically, and execute what can be
executed (chosen).** The declaration is the artifact's promise; the static
assertion enforces it for platforms the fleet cannot host; execution covers the
failures a symbol table cannot express. The three are complementary rather than
redundant, and the first is what makes the other two checkable.

**Switch the Linux target to musl.** Removes the glibc question outright, but
changes the runtime (allocator behaviour, NSS, dlopen) for every Linux user to
solve a build-configuration problem, and the embedded CPython distributions are
better supported on gnu. Rejected as disproportionate.

## Constraints

- The chosen floor is bounded below by what the embedded CPython distribution
  and the Rust toolchain support, and above by the oldest platform the project
  intends to serve. Any image at or under the floor works; the floor is the
  decision, the image is an implementation detail.
- The container build carries no remaining frontier risk: the full builder
  reproduces inside the pinned image and the artifact runs on the platform the
  published one cannot load on (`2026-08-28-binary-portability-research`). The
  image must have the toolchain provisioned into it, which is the only cost.
- Executing artifacts depends on the self-hosted fleet, which has no Intel
  macOS host and no host for any platform below the declared floor. The
  contract must therefore be satisfiable by static assertion alone for those.
- Embedding the project wheel depends on a PyApp capability that is documented
  but unused here; it also reorders the release, since the wheel must exist
  before the binaries are built rather than after.
- No macOS host was reachable during this work, so the macOS half of any
  execution gate is specified but unverified.

## Implementation

The contract is declared once, in the builder, as data: per target triple, the
minimum OS or libc version the artifact is required to load on. Everything else
reads that declaration rather than restating it.

For Linux, the build moves inside a container whose glibc is at or below the
declared floor, with the toolchain provisioned in the image rather than on the
host. The build then asserts the result against the declaration by reading the
artifact's own version requirements out of its dynamic symbol table and failing
when any exceeds the floor. That assertion is the part that must run for every
target the fleet cannot execute, and it is what converts an inherited property
into a checked one.

For the targets the fleet can host, the build additionally runs the artifact it
just produced and requires it to report its version. Because the artifacts
bootstrap from PyPI on first launch, this run is meaningful only once the
project wheel is embedded; until then the execution gate can prove the artifact
loads but not that it works, and the decision records that gap rather than
hiding it. Embedding the wheel is therefore sequenced first, which also makes
the artifacts standalone in the sense the documentation already claims.

Signing and notarization attach to the same enforcement point - a gate an
artifact passes before it may become a release asset - but are separate
decisions about what the gate checks, and are not settled here.

## Rationale

The knockout criterion is recurrence. Every option that repairs the current
artifact leaves the mechanism intact: the floor is a property of the build
host, and build hosts are upgraded by people who are not thinking about this
decision. Only declaring the floor in the repository and asserting artifacts
against it makes the property survive a runner upgrade, which
`2026-08-28-binary-portability-research` identifies as the actual cause.

Execution alone was rejected on the same evidence: the fleet's Linux host is
newer than every affected distribution, so smoke-running there reproduces
nothing. The static assertion is the only check that speaks for platforms with
no runner, and those are the majority of the supported set.

The cost of the chosen path is near zero at runtime, which the probe
establishes: pinning the floor keeps the pidfd path rather than compiling it
out, so no user loses anything.

## Consequences

The Linux artifact becomes loadable on the platforms the install documentation
names, and the floor becomes a reviewable line in the repository rather than a
property of a machine. A regression fails the release that introduces it
instead of reaching users.

The release gets slower and more coupled: a container pull on every Linux
build, an execution step per hosted target, and a wheel that must be built
before the binaries rather than beside them. The last of these is a real
reordering of the publish pipeline and is where the work is most likely to
stall.

Two gaps remain open by construction. The Intel macOS artifact stays unexecuted
until an Intel host exists or the target is dropped - and this decision makes
that choice explicit rather than incidental. And platforms below the floor are
covered only by the symbol assertion, which proves an artifact can load, not
that it behaves; closing that would need hosts the fleet does not have.

Making the binaries genuinely standalone opens the offline and air-gapped
install path the documentation already implies, and removes the release's
current dependency on PyPI propagation before its own artifacts work.
