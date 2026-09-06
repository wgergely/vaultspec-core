---
tags:
  - "#adr"
  - "#offline-binaries"
date: '2026-08-29'
related:
  - "[[2026-08-28-binary-portability-adr]]"
  - "[[2026-08-29-offline-binaries-research]]"
superseded_by: '2026-09-06-binary-bootstrapper-adr'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:dc44ef5b190391b9e447ce11b4251bc5483e185be0fb0c985f5e544b38d200e5'
---

# `offline-binaries` adr: `ship a prepared distribution and stop installing at first launch` | (**status:** `superseded`)

## Problem Statement

The release advertises standalone binaries that download 122 MB on first launch
and fail without a network. `2026-08-28-binary-portability-adr` established
that the artifacts' platform contract is declared and enforced at build time,
and recorded this gap without settling it: the binaries carry an interpreter
but not the code they run.

A decision is needed because the obvious remedy does not work and the working
remedy is not a build flag.
`2026-08-29-offline-binaries-research` shows that embedding the project wheel
leaves the dependency closure resolving from PyPI, so the download shrinks and
offline still fails - and that the option which genuinely disables installation
requires an artifact the release does not currently build, on a matrix where
one leg has no host of its own.

This record also settles the ordering against the pre-publish execution gate,
which is otherwise a natural thing to do first and would be nearly worthless
there.

## Considerations

- Embedding the wheel is not sufficient; all three project options are
  installation sources (`2026-08-29-offline-binaries-research`).
- Disabling installation is only meaningful with distribution embedding, and
  needs a distribution that already contains the application
  (`2026-08-29-offline-binaries-research`).
- The prepared distribution is per-target because three runtime dependencies
  ship native code (`2026-08-29-offline-binaries-research`).
- `macos-x86_64` is cross-built and cannot execute its own interpreter, so it
  cannot prepare an archive the way the other four legs can
  (`2026-08-29-offline-binaries-research`).
- The wheel must exist before the binaries build, inverting today's
  publish-then-build order (`2026-08-29-offline-binaries-research`).
- A pre-publish smoke run cannot distinguish "works" from "successfully
  fetched" while the artifact still installs at launch
  (`2026-08-29-offline-binaries-research`).
- Artifact size will grow and by how much is unmeasured
  (`2026-08-29-offline-binaries-research`).

## Considered options

**Embed the project wheel and call it done.** One option, no new artifact. It
is the remedy the issue proposes and it does not hold: the dependency closure
still resolves at launch, so the binary remains offline-hostile while now
*looking* addressed. Rejected as a fix that would close the issue without
changing the behaviour it reports.

**Vendor the dependencies into the wheel.** Avoids a prepared distribution by
making the project wheel self-contained. It fights the packaging ecosystem -
native wheels per platform and interpreter, no supported way to express that in
one distribution - and puts the fleet in the business of repackaging other
people's builds. Rejected as disproportionate and fragile.

**Prepare a per-target distribution and skip installation (chosen).** Each leg
builds an archive that is the stock python-build-standalone distribution with
the application and its dependency closure installed into it, and the binary is
built against that with installation disabled. It is the only option that makes
the artifact match the claim, and it is what PyApp documents for exactly this
purpose.

**Drop the "standalone" claim instead.** Honest, free, and available at any
time. Rejected because the binary channel exists to serve the case Python
install channels cannot - an offline or air-gapped host - so retreating on the
claim retires the channel's reason to exist rather than fixing it.

## Constraints

- The `macos-x86_64` leg is the frontier risk. It must assemble a foreign
  platform's archive without executing that platform's interpreter - resolvable
  with explicit platform tags and binary-only wheels, but it is a materially
  different path from the other four and the one most likely to yield a subtly
  wrong archive. It is also the leg that is executed nowhere, so a defect there
  has no other net beneath it.
- No Intel macOS host and no reachable Apple host at all, so that leg cannot be
  verified by running it. Any confidence there comes from inspection.
- The release must be reordered so the wheel precedes the binaries. That is a
  change to the publish pipeline, not to `binaries.yml` alone.
- Skipped installation removes the `update` command unless deliberately
  re-exposed; whether that is wanted is not settled here.
- Artifact growth is unmeasured and could be material on every download.
- The floor work from `2026-08-28-binary-portability-adr` still applies: the
  prepared archive is built inside the pinned container on the Linux legs, so
  the declared glibc floor continues to hold.

## Implementation

Each build leg gains a preparation step before the PyApp build. It takes the
stock distribution for its target, installs the project wheel and its full
dependency closure into that distribution's own site-packages, and re-archives
the result. The PyApp build then points at that archive and disables runtime
installation, so the binary contains an interpreter, the application, and every
dependency, and reaches first launch with nothing left to fetch.

The wheel is built once, before the matrix, and passed to every leg - which is
what reorders the release: the distribution artifact is produced from the wheel
rather than from a published index, so publication stops being a precondition
of the binaries and becomes a peer of them.

The cross-built leg prepares its archive by resolution rather than execution,
selecting wheels for the foreign platform explicitly instead of letting the
host interpreter decide. That difference is confined to that one leg and is
stated in the build script rather than discovered from its behaviour.

Once installation is skipped, the pre-publish execution gate becomes worth
adding: each artifact the fleet can host is run before it is attached to a
release, and because nothing is fetched, a pass means the shipped bytes work.
That gate is the subject of the issue this decision unblocks rather than
something this record implements.

## Rationale

The knockout is that the cheap option does not change the reported behaviour.
Embedding the wheel would let the issue be closed while a user on an
air-gapped host still cannot start the binary - the failure the channel exists
to prevent. An option that leaves the symptom intact is not a smaller version
of the fix; it is a different outcome wearing its name.

Preparing the distribution is chosen over vendoring because it uses the
mechanism PyApp provides for this exact case, and keeps platform-specific
resolution in the packaging tools that own it rather than reimplementing it.

The ordering against the execution gate follows from the same fact. While the
artifact installs at launch, a smoke run on a connected runner proves the
network works; after this, the same run proves the artifact does. Doing the
gate first would buy a green check that asserts almost nothing.

## Consequences

The binaries become what they are advertised as, and the offline and
air-gapped install path the documentation implies becomes real. The release
stops depending on PyPI propagation before its own artifacts function, which
removes a timing coupling that has no upside.

The costs are concentrated and worth stating plainly. Every leg gains a
preparation step, so the release gets slower. Artifacts get larger by an amount
nobody has measured yet, and that lands on every download. The cross-built
Intel macOS leg acquires a second way to be wrong - a foreign-platform
resolution - on the one target that is executed nowhere, which is the least
comfortable part of this decision and the first place to look if a released
binary misbehaves.

It also opens the pre-publish execution gate, which is the point: that gate is
cheap and meaningful afterwards, and neither before.
