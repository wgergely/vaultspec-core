---
tags:
  - "#adr"
  - "#binary-bootstrapper"
date: '2026-09-06'
related:
  - "[[2026-08-29-offline-binaries-adr]]"
  - "[[2026-08-28-binary-portability-adr]]"
  - "[[2026-08-29-offline-binaries-research]]"
  - "[[2026-08-28-binary-portability-research]]"
supersedes:
  - '2026-08-28-binary-portability-adr'
  - '2026-08-29-offline-binaries-adr'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:88d487f9540c9fa4e048407efda7249adbeeecc291298dfa820cd013ece4fb74'
---

# `binary-bootstrapper` adr: `the release binary is a bootstrapper and the documentation says so` | (**status:** `accepted`)

## Problem Statement

The release binaries are described as standalone in four places, and the word is false.
The artifact carries its interpreter - `dev/binaries/build_pyapp.py:149` sets
`PYAPP_DISTRIBUTION_EMBED=1`, shipped since v0.1.55 - but it installs the application
and its dependency closure at first launch with `uv`, which it also fetches
(`dev/binaries/build_pyapp.py:146`). On a host with no network the binary does not
start.

A decision is needed because two records already exist for this gap and neither
resolves it. `2026-08-28-binary-portability-adr` names the false claim among its
considerations, and `2026-08-29-offline-binaries-adr` chooses to make the claim true by
preparing a per-target distribution and disabling installation, listing "drop the
standalone claim instead" among the options it rejects. Both remain `proposed`. Neither
has been built. In the interval the documentation continues to tell users something
untrue, and the correction has been held on the theory that making the claim true would
make correcting it unnecessary.

This record settles the narrower question those two leave entangled: what the
documentation says while the artifact is what it is.

## Considerations

- The interpreter is embedded and the first launch still fetches `uv` and the dependency
  closure (`dev/binaries/build_pyapp.py:146`, `dev/binaries/build_pyapp.py:149`).
- `docs/channels.md:6` already disclosed the network requirement accurately, so the
  repository was internally inconsistent rather than uniformly wrong.
- A `proposed` record is an intention, not a commitment the code owes; the status
  vocabulary in `src/vaultspec_core/core/enums.py:47` distinguishes the two
  deliberately.
- Accurate wording and a prepared distribution are independent: neither blocks the
  other, and the wording is reversible in an afternoon.
- The rejection of "drop the standalone claim" in `2026-08-29-offline-binaries-adr` was
  a rejection of it as a substitute for the engineering, not as a description of the
  artifact that exists.
- No user has yet asked for offline operation, and none has been shown to exist; the
  claim's falsity, by contrast, is observable today.

## Considered options

**Hold the wording until a prepared distribution ships.** Keeps a single consistent
story and needs no supersession. Rejected: it makes the accuracy of the documentation
depend on unscheduled work of unmeasured size, on a matrix with one leg the fleet cannot
execute, and every user reading the claim in the interval is misled.

**Accept `2026-08-29-offline-binaries-adr` and build it now.** Makes the claim true
rather than retracting it. Not rejected on merit - it remains the better end state - but
it does not answer what the documentation says in the meantime, and adopting it as the
answer to this problem would be adopting a schedule as a fact.

**Mark both prior records `rejected`.** Cheap and tidy. Rejected because it records the
wrong thing: the engineering in those records was not found wrong, it was not taken up.
`rejected` would tell a future reader the approach was considered and declined on merit,
which is the opposite of the case.

**Correct the wording now and supersede the two proposed records as an intention not
taken up (chosen).** The documentation describes the artifact that exists; the two
records stop presenting an unbuilt route as the pending state of the repository; the
route itself is preserved as an issue rather than dying with them.

## Constraints

- Supersession is the only lifecycle verb that both retires a record and names its
  successor (`src/vaultspec_core/core/adr.py:174`); it rewrites the H1 token to
  `superseded` regardless of the prior token, so `proposed` records pass through it
  correctly.
- Superseding a record does not preserve its engineering elsewhere. The
  prepared-distribution work must be re-homed before these two stop being read, or it is
  lost with them.
- The wording correction is the whole of the change on this side: no build, workflow, or
  signing surface is touched, so nothing here alters what the artifact does.
- The landing-page copy lives in a separate, private repository and cannot be corrected
  from here; it carries the same claim and remains wrong until it is.
- Any future offline claim needs a `--network none` execution to back it. A networked
  invocation asserts nothing about the property, and adding one would be the
  false-assurance shape this repository keeps removing.

## Implementation

Four locations stop calling the binaries standalone and say what they are: `README.md:43`
and `docs/framework.md:209` describe binaries that need no separate Python install but
need network on first launch; `docs/channels.md:6` extends its existing disclosure to
name `uv` as fetched and to say later launches are local; `docs/channels.md:59` and the
builder's module docstring in `dev/binaries/build_pyapp.py:1` follow. Two residual uses
of the word inside `dev/binaries/` are corrected with them so the subsystem does not
contradict its own docstring.

`2026-08-28-binary-portability-adr` and `2026-08-29-offline-binaries-adr` are superseded
by this record. The portability record's floor and static-assertion work is untouched by
that: it was never built either, and the reason it retires here is the same as the
offline record's - it is an intention the repository did not take up, and its sequencing
premise, that embedding the wheel comes first, is the premise this record declines.

The prepared-distribution route is filed as its own issue, carrying the parts of both
records that are engineering rather than intention: the per-target distribution,
`PYAPP_SKIP_INSTALL`, the release reordering that puts the wheel before the binaries,
and the `--network none` gate that would make the resulting claim checkable. That issue
is GitHub issue #482, and it is where the idea lives now.

## Rationale

The knockout is that the two positions are not in competition. The proposed records
answer what the artifact should be; this one answers what the documentation should say
about the artifact that exists. Only the second question has a live cost, and its answer
does not constrain the first: if a prepared distribution ships, these same five lines
change back, cheaply and with the claim true.

Holding the correction loses on the same asymmetry. Its price is paid continuously by
every reader, and its benefit - never editing the wording twice - is worth less than one
afternoon. It also inverts the ordinary relation between records and code: a `proposed`
ADR was being treated as authority over what the repository may say about itself, which
is a status it does not have.

Supersession rather than rejection is chosen because the record's value to a future
reader is its reasoning, and that reasoning survives. The per-target distribution
analysis, the native-wheel finding, and the release-ordering consequence are all still
correct; what changed is that nobody committed to them.

## Consequences

The documentation matches the artifact, and the repository stops contradicting itself
between `docs/channels.md` and everything else. A reader who needs an offline install
now learns that this channel is not one, which is worse news delivered honestly and
earlier than a failed first launch on an air-gapped host.

The binary channel loses its stated reason to exist for the air-gapped audience, which
is the cost `2026-08-29-offline-binaries-adr` predicted and named. That audience is
served by nothing here: `uvx` needs the network too. If any such user surfaces, the
filed issue is the response and this record does not stand in its way.

Two `proposed` records leave the queue without their work being done, and the vault will
show that as supersession rather than as completion. That is the accurate shape and the
reason the issue exists: the next person to want offline binaries starts from the
analysis rather than from `PYAPP_PROJECT_PATH`.
