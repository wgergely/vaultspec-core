---
tags:
  - '#adr'
  - '#publisher-identity'
date: '2026-09-05'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:16275d54a2fe313cb6756a1958d4faf49254ccd7ed78bc09beac227b5d710917'
related:
  - "[[2026-09-05-publisher-identity-research]]"
  - "[[2026-08-28-binary-portability-adr]]"
---

# `publisher-identity` adr: `attest provenance now; defer publisher identity to a route that costs nothing` | (**status:** `proposed`)

## Problem Statement

`2026-08-28-binary-portability-adr` declared what a target triple entitles a user to
expect and enforced it at build time, and left one question open in terms: signing and
notarization attach to the same enforcement point but are separate decisions about what
that gate checks. This record settles that question.

It needs settling now for two reasons that pull in opposite directions.
vaultspec-core#342 and vaultspec-core#336 have measured the gap on both platforms, so it
is no longer a suspicion; and `2026-09-05-publisher-identity-research` establishes that
the remediation both issues prescribe cannot be bought as written. Leaving the question
open therefore leaves a documented gap whose documented fix does not exist, which is the
condition under which someone eventually implements the fix anyway and discovers only
afterwards that it signs nothing.

## Considerations

- The prescribed remediation is unpurchasable: no CA issues a key in the form both
  issues ask for (`2026-09-05-publisher-identity-research`).
- The premium option's justification has lapsed; EV and OV now behave identically for
  the property that motivated it (`2026-09-05-publisher-identity-research`).
- Reputation accrues to an identity across releases, so releasing under none accrues
  nothing indefinitely rather than improving with age
  (`2026-09-05-publisher-identity-research`).
- One route removes both the funding and the hardware obstacle, at the cost of process
  obligations and an outcome decided by someone else
  (`2026-09-05-publisher-identity-research`).
- A weaker guarantee is available immediately, requires no identity, and answers a
  question checksums cannot (`2026-09-05-publisher-identity-research`).
- The exposed population is narrower than unsigned status alone implies, and the
  documented Windows install path is not in it
  (`2026-09-05-publisher-identity-research`).
- The two platforms are not symmetric: one has a route costing nothing, the other has a
  floor that does not go to zero (`2026-09-05-publisher-identity-research`).

## Considered options

- **Buy a certificate now.** Rejected on cost, and separately on availability: the
  cheapest hosted route is bounded by eligibility rather than price, and the cheapest
  certificate binds signing to one physical machine.
- **Sign with a self-generated certificate.** Rejected. It changes the reported status
  without changing any user-visible behaviour
  (`2026-09-05-publisher-identity-research`), and a signing step whose output nothing
  trusts is capability-shaped dead code of exactly the kind this repository has removed
  before.
- **Write the signing wiring now, inert, against a credential that may arrive.**
  Rejected on the same grounds and one more: it could not be executed even once, so it
  would be committed unverified and would read as a solved problem in the file where a
  reader looks to see whether the problem is solved.
- **Attest build provenance and record the remaining gap.** Chosen. It is buildable
  today, verifiable by a user, and makes a claim it can actually support.
- **Do nothing and leave the issues open.** Rejected. It concedes the verification that
  was available for free, and it leaves a documented remediation in place that cannot be
  performed.

## Constraints

The chosen half depends on no unavailable capability: attestation is a first-party
GitHub action against a public repository, and the signing identity it does not provide
is precisely the part being deferred.

The deferred half is blocked on an input this repository cannot produce. Its arrival is
decided by a third party over an unbounded interval and may not arrive at all, so no
work may be sequenced behind it and no file may be written in anticipation of it.

The conditions attached to the free route are process obligations - a published signing
policy, multi-factor authentication, per-release manual approval - which must be met
before that route can be taken and which are stated here as conditions that exist, not
as an assessment of any current state.

The parent decision, `2026-08-28-binary-portability-adr`, is stable in the part this
record relies on: it established the pre-publication gate that attestation now attaches
to, and that gate is in service.

## Implementation

Provenance is minted in a dedicated job that holds the signing credential and nothing
else, and no artifact may become a release asset unless that job succeeded. The ordering
is still the enforcement; it is a job edge rather than step ordering, because the
alternative put a capability that mints OIDC tokens for any audience in the same job as
the channel deploy key and the packaging code that generates the distribution pointers.
Those two do not compose - an SSH key is not federated by any token - but the widest
credential in the repository sat in its most crowded job for no reason beyond that being
where it was first written. Every attached asset is then re-verified against the
published record, against the subject set the signing job reports rather than one the
verifying job derives for itself, which is what distinguishes an attestation that was
made from one that was merely attempted.

One field of the record is knowingly wrong, and is recorded here so it is not later
rediscovered as a defect. The predicate carries the runner environment of the job that
signed, not of the job that built; the build matrix is mixed, and each leg emits two
binaries, so attesting from the self-hosted fleet describes the two artifacts of the
single hosted leg as self-hosted. The alternatives were weighed and are worse: signing
on a hosted runner would misdescribe the other six instead, and signing inside each
build leg - the only shape under which the field is true everywhere - would spread the
token-minting capability across four jobs, two of which run as root in a reused
workspace and compile a third-party crate tree. The inaccurate field is one no verifier
reads, and it has an independent path to becoming true: moving that leg onto the fleet
is already proposed and is blocked on a host change rather than on anything in the
release workflow. A token-minting capability in three more jobs has no path to shrinking
on its own, which is what settles the trade.

Both checks refuse to pass vacuously. An empty artifact set fails rather than attesting
nothing, and a verification pass that examined no asset fails rather than reporting
success - the shape this repository has been bitten by before, most visibly in the
release that published blank digests out of a green run.

Placement of the two checks differs deliberately. Attestation gates upload because an
asset that cannot be attested should not exist; verification runs last because an
unattested asset is still a working asset, and withholding a functioning download to
punish missing metadata would cost users more than the gap does.

The user-facing documentation states both what can be verified and what the verification
does not prove, because the failure mode of overclaiming here is a user who believes the
download is signed and therefore stops checking. It also states WHEN, which is the
overclaim this record made on its first pass: the wiring was documented as though it
were already producing verifiable assets while every published release predated it, so
the documented command failed for every download a user could obtain. A security
instruction that reliably fails teaches people to skip security instructions, which
costs more than the gap it was covering. The documentation now names the first release
that will carry provenance, and a repository guard fails once that release is cut so the
qualification cannot outlive the condition it describes.

The deferred half acquires no wiring. What it acquires is a named trigger: the free
route in `2026-09-05-publisher-identity-research`, whose outcome converts this record's
accepted risk into implementable work.

## Rationale

The knockout criterion is whether a claim can be supported. Every rejected option either
cannot be executed or produces a signal that means less than it appears to: the
unpurchasable one cannot be built at all, the self-generated one produces a status that
no user-visible mechanism honours, and the inert one produces a file that reads as
capability while doing nothing. Only the chosen option makes a statement the project can
stand behind, which is the same criterion `2026-08-28-binary-portability-adr` applied
when it rejected repairs that left the recurrence intact.

Attestation and signature are frequently conflated, and the decision turns on their
difference. They answer different questions - where an artifact came from, versus who
vouches for it to the operating system - and only the first is answerable without a
purchased identity. Treating the answerable half as worthless because the unanswerable
half is blocked would have conceded a real verification the project could offer for
free.

Deferring rather than accepting permanently is what the third option preserves. The
research establishes a route whose price is process rather than money, which makes the
gap contingent rather than structural; recording it as accepted risk without naming that
route would have made a temporary condition look permanent.

## Consequences

A user can establish that a release asset came from this repository and this workflow
run, without trusting the page it was downloaded from - a check that did not exist
before and that no amount of checksumming provides. The release cannot ship an asset it
failed to attest, and cannot report success having attested nothing.

The gap that remains is stated rather than implied. Operating-system trust is unchanged
on both platforms: the browser-download-and-launch path still meets an interstitial, and
a managed fleet still has only per-file rules to express an allowance. Anyone reading
this repository for whether its binaries are signed gets an unambiguous no, together
with what is offered instead.

The macOS half stays open on a floor this decision does not lower, and is deliberately
not resolved by implication here. Recording that asymmetry is the point: a reader who
sees the Windows question settled would otherwise reasonably assume the other one
travelled with it.

The pitfall this record most needs to survive is being read as a to-do. It is not.
Signing wiring written before the identity exists is the outcome this decision rejects,
and a future reader who finds the deferred half unimplemented is looking at the decision
working rather than at work left undone.

The deferral has since been closed in the direction this record left open. Publisher
identity is settled as not planned - the issues tracking it on both platforms are closed
without work, because a paid per-year identity tied to a legal entity is not something
this project buys. Nothing in the chosen half changes; what changes is its standing.
Attestation is no longer the available half of a two-part answer whose other half is
pending. It is the whole verification story, so the operating-system friction recorded
above is permanent and is documented as permanent, and a weakness in the attestation
lane is now a user-facing defect rather than a shortfall in a supplementary check.
