---
tags:
  - '#adr'
  - '#gemini-live-guards'
date: '2026-09-06'
modified: '2026-09-06'
body_schema: 'body-v2'
body_hash: 'sha256:2a1e57734b7f335355eb07bc6c183977b85b3159f814900fc23204e442f952e8'
related:
  - '[[2026-09-06-gemini-live-guards-research]]'
---

# `gemini-live-guards` adr: `Retire the Gemini live test and drift guards; keep the model-drift workflow` | (**status:** `accepted`)

## Problem Statement

Core verified its Gemini agent-render contract against live upstream twice: once by shelling out to a real `gemini` binary, once by fetching a source file from the `google-gemini/gemini-cli` repository. Both were designed as opt-in and, until `#483`, both ran on every default test invocation.

The Gemini CLI is a deprecated upstream product, which changes what those guards are worth. A conformance test against a binary that will stop being installable fails on a schedule Core does not control, for a reason unrelated to Core's correctness. Separately, the network guard's ref had already been pinned to a tag, which silently removed its ability to detect anything.

The related question - what becomes of the Gemini *provider* - is deliberately **not** decided here. This record covers only the test and CI surface, because that cost is real today and its answer does not depend on the provider's future. The grounding is `2026-09-06-gemini-live-guards-research`.

## Considerations

- `TestGeminiCliLoadsRenderedAgents` is a good probe. Its invalid-agent canary defends against a false green, so removing it is a loss, not a cleanup (`2026-09-06-gemini-live-guards-research`).
- `TestUpstreamGeminiToolPin` compares an immutable tag against an unchanged enum. Its result is constant; the only reachable failures are network faults (`2026-09-06-gemini-live-guards-research`).
- Everything else in the module is offline and deterministic, and covers the parts most likely to regress: the tool-vocabulary mapping, the host-tool drops, and the per-agent render of every shipped source agent.
- `GeminiModels` (`core/enums.py:137`) names Google **model API** identifiers, not CLI versions, and `AntigravityModels` (`:172`) mirrors it value-for-value. The Google model lineup belongs to a live provider and to a lifecycle independent of the CLI.
- `model-drift.yml` also covers Anthropic and OpenAI, and is dormant: manual dispatch only, no schedule, and dependent on a secret its own header records as absent.
- Antigravity and Gemini are not the same provider under two names. They share `.agents/skills/` and `GEMINI.md` and diverge on everything else, including Antigravity having no agents capability at all (`2026-09-06-gemini-live-guards-research`). Any decision that treats one as an alias of the other needs its own record.

## Considered options

- **Keep both guards (rejected).** Keeps a binary dependency that will break for reasons unrelated to Core, and keeps a network guard that cannot detect drift.
- **Remove the binary probe only (rejected).** Answers the stated cost but leaves a test that reads like a drift guard and is not one. A guard that cannot fail informatively is worse than no guard, because a reader trusts it.
- **Remove both live guards, keep everything offline (chosen).** Removes the external dependency entirely and leaves the module deterministic, at the cost of no longer proving a rendered agent loads.
- **Delete `model-drift.yml` (rejected).** Checking what it covers changed the answer: its subject is vendor model lineups, and the Google lineup is Antigravity's. Deleting it would strip tracking a live provider depends on.
- **Remove the Google registry from `model-drift.yml` (rejected).** Same objection, narrower. `AntigravityModels` must mirror `GeminiModels`, so the Google half is not the Gemini CLI's half.

## Constraints

- No provider behaviour may change. This record touches tests and workflow prose only; `Tool.GEMINI`, the renderers, sync, uninstall and the managed-block policy are untouched.
- The `gemini` and `network` marker registrations in `pyproject.toml` and `dev.toolchain.EXCLUDED_MARKERS` are owned by `#483`, which bound them together behind a guard. This record leaves both alone; after it, neither marker has a user, which is for that work to reconcile.
- The `GeminiBuiltinTool` vocabulary becomes unverified against upstream. It is frozen at `v0.47.0` and its docstring must say so, or the next reader will assume a check exists.

## Implementation

Two live test classes are removed from `src/vaultspec_core/tests/cli/test_agents_render.py`, along with the imports and constants that served only them. What remains is the offline contract in full: every shipped source agent is rendered for Gemini, every emitted tool name is asserted to be in the `GeminiBuiltinTool` vocabulary, and the Claude-to-Gemini mapping and host-tool drops are asserted directly. The module then reaches neither network nor subprocess, so its module-level `unit` marker is accurate rather than aspirational.

Two docstrings that pointed readers at the removed pin - on `GeminiBuiltinTool` and on the tool mapping - now record that the vocabulary is frozen against `v0.47.0` and that nothing re-checks it, so the absence of a guard is stated rather than discovered.

`model-drift.yml` keeps its job and gains three prose corrections: a scope note recording that it tracks vendor model lineups rather than CLI products and why the Google registry stays, an explicit instruction that a Google drift PR is not licence to grow the Gemini provider, and a repair to an instruction that named a file whose tier fixtures are Claude-only.

## Rationale

The two guards fail for different reasons and the reasoning has to be separate, which is why removing only the one the issue named would have been the wrong shape.

The binary probe is removed on a dependency argument: it is correct today and will fail tomorrow for a reason that says nothing about this repository. Keeping it means accepting an unbounded future failure in exchange for a check on a product being retired.

The upstream pin is removed on a truthfulness argument, which is stronger. Once its ref was pinned to a tag it stopped being able to observe drift, so its green result carries no information. A test that reads like a guard and asserts nothing is the failure mode this repository objects to elsewhere; leaving it in place would let a future reader conclude the vocabulary is still verified.

Keeping `model-drift.yml` follows from reading it rather than from its name. Its subject is the three vendor model lineups, and `AntigravityModels` mirrors `GeminiModels` value-for-value, so the Google registry serves a current provider. "Retire the Gemini half" has no referent there - the CLI product appears in that workflow only as a name.

## Consequences

The suite no longer depends on any provider binary or on network reachability, and the Gemini render module runs in about a second rather than waiting on a subprocess with a three-minute timeout.

What is lost is real and worth stating plainly: nothing now proves a rendered agent is accepted by a `gemini` loader. The offline vocabulary check is a proxy - it proves Core emits only names the enum declares, not that the enum still matches the binary. If the frozen enum is wrong, no test in this repository will say so, and the only defence is the docstring saying it is frozen.

`gemini` and `network` were left registered with no users. That was deliberate rather than overlooked: the registration and the exclusion list are bound together by a guard belonging to other work, and reconciling them from here would have edited a contract this record does not own. `#490` has since done that reconciliation - both markers and both `addopts` exclusions are gone, `dev.toolchain.EXCLUDED_MARKERS` is `not claude` alone, and a bare `pytest` was verified to collect the same set afterwards.

This record settles the test and CI surface and nothing else. The provider's future - freeze, deprecate, or succeed by Antigravity - remains open, and the grounding research establishes the constraint any of those answers has to satisfy: Antigravity is not Gemini under another name, so a rename is not a label change.
