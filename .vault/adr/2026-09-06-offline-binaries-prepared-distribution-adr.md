---
tags:
  - "#adr"
  - "#offline-binaries"
date: '2026-09-06'
related:
  - "[[2026-09-06-binary-bootstrapper-adr]]"
  - "[[2026-09-06-offline-binaries-prepared-distribution-research]]"
  - "[[2026-08-29-offline-binaries-adr]]"
  - "[[2026-08-29-offline-binaries-research]]"
  - "[[2026-08-28-binary-portability-adr]]"
supersedes:
  - '2026-09-06-binary-bootstrapper-adr'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:b6783228d46575768b964298b5a39acb1f5d67ef6da5378b40a66acdfaa2c7fe'
---

# `offline-binaries` adr: `bake a per-target distribution and gate it with --network none` | (**status:** `accepted`)

## Problem Statement

`2026-09-06-binary-bootstrapper-adr` corrected four places that called the release
binaries standalone, on the finding that the artifact installs its application and
dependency closure at first launch and cannot start without a network. That record is
accurate about the artifact that existed and explicitly names the better end state it
was not choosing between: making the claim true rather than retracting it.

A decision is needed because the engineering it deferred is now measured rather than
estimated, and the two things that made it look expensive have both moved.
`2026-09-06-offline-binaries-prepared-distribution-research` shows that the frontier
risk `2026-08-29-offline-binaries-adr` named - a cross-built leg assembling a foreign
platform's archive without executing it - no longer exists on this matrix, and that the
size cost it left unmeasured is roughly a doubling rather than an unknown.

The other half is that the claim needs a check. #340 happened because nothing in the
pipeline ever took the network away, so a green `--version` on a connected runner
asserted the property and its opposite equally well. A prepared distribution without
that check would be the same defect with a different default.

## Considerations

- `PYAPP_SKIP_INSTALL` alone leaves the `uv` download in place; full isolation is what
  removes it (`2026-09-06-offline-binaries-prepared-distribution-research`).
- A distribution supplied by path carries no layout defaults, and PyApp fails the build
  rather than guessing (`2026-09-06-offline-binaries-prepared-distribution-research`).
- The artifacts grow by 25-31 MB each, 1.8x to 2.3x
  (`2026-09-06-offline-binaries-prepared-distribution-research`).
- Every release leg builds natively, so nothing that ships is cross-resolved
  (`2026-09-06-offline-binaries-prepared-distribution-research`).
- `--network none` is reachable on both Linux legs, but only from outside a container
  job (`2026-09-06-offline-binaries-prepared-distribution-research`).
- Windows has no unprivileged per-process network isolation
  (`2026-09-06-offline-binaries-prepared-distribution-research`).
- The dependency closure is per-target because three dependencies ship native code
  (`2026-08-29-offline-binaries-research`).
- The wheel must exist before the binaries, which reorders the release
  (`2026-08-29-offline-binaries-research`).

## Considered options

**Prepare the distribution and gate it where a network namespace exists (chosen).** Each
leg installs the wheel and its closure into the stock python-build-standalone archive
for its target, and the binary is built against that with installation disabled. Every
artifact is then run with the strongest isolation its platform offers before it may
become a release asset. Makes the claim true and makes it checkable, at the cost of a
substantially larger download and one platform whose check is weaker than the others.

**Prepare the distribution and skip the gate.** Cheaper, and the property would very
likely hold. Rejected on the grounds this repository has already paid for once: the
artifact and the claim about it are different objects, and #340 is what an unchecked
claim looks like eighteen months later. A prepared distribution that nobody runs offline
is a claim, not a property.

**Gate first, prepare later.** The ordering `2026-08-29-offline-binaries-adr` already
settled and it still holds: while the artifact installs at launch, a `--network none`
run fails by design, so the gate can only be added after the thing it checks.

**Take the network away with an `LD_PRELOAD` shim instead of a namespace.** Would let
the check run inside the existing containerised build legs, where `unshare` is refused.
Rejected: it intercepts libc entry points rather than removing the network, so it is
weaker evidence than the thing it would replace, and it introduces a C artifact into a
build that currently needs no compiler of its own.

**Leave the documentation correct and the artifact as it is.** Free, and the status quo.
Rejected because the binary channel exists to serve the case the Python channels cannot,
and `2026-09-06-binary-bootstrapper-adr` records that it currently serves nobody in
particular - it is a slower `uvx` with a larger download.

## Constraints

- The Windows leg's offline property is asserted rather than isolated. What is missing
  there is a second measurement of a property already measured on two other platforms
  through the same shared code path, not the only measurement of it - but it is a real
  gap and it is the first place to look if a Windows binary misbehaves offline.
- The gate lives in the release workflow, which runs on a tag. It cannot be exercised
  without cutting a release, so its first real run is the first release after this
  lands. The mechanism was reproduced by hand end to end before landing - the published
  v0.1.73 artifact failing offline and a locally built one passing - which is evidence
  the check works, not evidence that this workflow file runs it.
- The wording in `README.md`, `docs/channels.md` and `docs/framework.md` becomes true of
  binaries built from this commit onward, not of the binaries currently published. The
  interval between merging and the next release is a window in which the documentation
  runs ahead of the artifact, in the opposite direction from the one
  `2026-09-06-binary-bootstrapper-adr` closed. The acquisition check's retry loops are
  removed in the same interval and for the same reason, so a dispatch of that workflow
  against a release cut before this lands is checking a bootstrapper with the tolerance
  a bootstrapper needed taken away.
- The Windows gate cannot force a cold start the way the Unix legs do. PyApp resolves
  its data directory through the known-folder API rather than through `LOCALAPPDATA`, so
  the redirection that leg performs may be ignored; what makes the run cold there is
  that the directory is per-version and the version has never run on the host. The
  assertion about what was fetched searches both roots rather than assuming which one
  was used.
- The declared `GLIBC_2.28` floor and its static assertion are untouched and still
  apply; the prepared archive is assembled inside the same pinned image.
- Skipping installation removes `self update` unless `PYAPP_ALLOW_UPDATES` re-exposes
  it. It is deliberately not re-exposed: an update would install from an index into an
  artifact whose whole premise is that it does not, and it would desynchronise the
  bytes from the digest the channel pointer and the attestation describe.
- The size increase lands on every download, on every platform, forever. It is the
  largest cost here and the one with no mitigation short of dropping a dependency.

## Implementation

Each build leg gains a preparation step ahead of the PyApp build. It fetches the stock
python-build-standalone archive for its target, installs the project wheel and its
entire dependency closure into that distribution's own `site-packages` with binary
wheels only, and re-archives the result with fixed entry order, ownership and
timestamps. The binary is then built against that archive with installation disabled
and full isolation on, so it unpacks and runs rather than unpacking and installing.

The archive is made deterministic, which is not the same as claiming the release binary
is reproducible - the Rust compile around it is not controlled here and no check
compares two builds of one tag. Determinism at this layer is taken because it is cheap:
the tar metadata is normalised, and the PEP 610 record of where the wheel sat on the
build machine is dropped, so the same wheel prepared on two hosts yields one archive
rather than two that differ by a path.

The wheel is built once, before the matrix, and passed to every leg. That is what
reorders the release: the binaries are made from the tag rather than from an index, so
publication stops being a precondition of them and becomes a peer.

The gate is a second matrix over the same targets, and an artifact reaches a release
only through it. The build leg uploads under a name nothing downstream attaches; the
gate renames it on success. A leg that fails is therefore excluded from the release by
the same mechanism that already handles a leg that failed to compile, without the
attach job needing to know a gate exists. The Linux legs run the artifact under
`docker run --network none` in the image it was built in, macOS under a seatbelt profile
that denies the network, and Windows with every proxy variable black-holed. Each begins
by proving its own isolation works, so a check that stopped isolating fails rather than
passing vacuously.

The settings that make the artifact offline are pinned in `dev/binaries/tests` against
every target, and `ci.yml` asserts on every pull request that the build matrix and the
gate matrix cover the same targets - the derivation this repository has twice had to
add after a hand-kept list drifted.

## Rationale

The knockout is that the check is the deliverable. Everything else here is
configuration: two PyApp options, an archive, and an ordering. Configuration is cheap to
get right and equally cheap to lose, and the way this repository loses it is not by
being wrong but by having nothing that notices. The prepared distribution answers #482;
the `--network none` run is what stops #340 recurring, and it is worth more than the
distribution it verifies because it would have caught the original defect against the
original artifact.

Full isolation is chosen with skipped installation rather than instead of it because the
research shows the two are not alternatives: the virtual-environment path fetches `uv`
before it ever reads the skip flag. That is the single fact most likely to be
rediscovered painfully by someone setting one option and testing on a connected machine.

The Windows asymmetry is accepted rather than closed because both ways of closing it are
worse than the gap. A firewall rule needs administrator rights on a shared host and can
survive a cancelled job; a Windows container is infrastructure this fleet has not been
shown to have. Naming the weaker leg costs nothing and misrepresenting it would cost the
same as #340 did.

## Consequences

The binaries become what the documentation says, and the offline and air-gapped path the
channel exists to serve becomes real rather than implied. The release stops depending on
PyPI propagation before its own artifacts function, which removes a timing coupling with
no upside - and with it the ten-minute retry loops in the acquisition check that existed
only to wait that propagation out. Those loops would now hide the very regression this
record guards against, so they are gone.

The costs are concentrated and worth stating plainly. Every download roughly doubles:
30 MB more on Linux x86-64, 31 MB more on Windows, 25 MB more on Apple Silicon. Most of
that is `numpy`, which `rustworkx` requires and which nothing here can decline. The
release gets slower by a preparation step and a gate job per target, on a shared
self-hosted fleet. And the matrix is now written twice, which is a drift risk this
repository has been bitten by twice before - mitigated by an assertion rather than
removed, because GitHub offers no way to share one matrix between two jobs.

The gate opens as much as it closes. It is the first thing in this pipeline that
executes an artifact under conditions a user might actually have, which makes it the
natural place to add the platform-specific execution the portability work wanted and
never got. What it does not do is speak for Windows as strongly as it speaks for Linux,
and that is the residual gap this record leaves open on purpose rather than by omission.
