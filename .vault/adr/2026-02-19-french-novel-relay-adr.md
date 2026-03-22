---
tags:
  - '#adr'
  - '#french-novel-relay'
date: '2026-02-19'
related:
  - '[[2026-02-19-french-novel-relay-test-research]]'
  - '[[2026-02-15-cross-agent-adr]]'
  - '[[2026-02-15-a2a-adr]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `french-novel-relay` adr: 3-Turn Collaborative French Novel Relay Test via A2A | (**status:** `accepted`)

## Problem Statement

The A2A protocol test suite validates bidirectional agent communication using
exact-match fingerprint tokens (`GEMINI_CONFIRMED`, `CLAUDE_RECEIVED_GEMINI`)
in 2-turn sequential chains. No test exercises multi-turn creative relay where
agents produce meaningful narrative prose that builds on prior context. The
existing `TestGoldStandardBidirectional` comment explicitly defers true
cross-delegation to "Phase 6 scope." The Jean-Claude persona and Le Croissant
Solitaire story corpus exist as test fixtures but are never used for
collaborative content generation between agents.

## Considerations

Three design options were evaluated in
\[[2026-02-19-french-novel-relay-test-research]\]:

- **Option A (Mock Only):** `StoryRelayExecutor` test doubles produce
  deterministic French chapter templates. Fast and cheap but tests plumbing,
  not real agent reasoning or French language output.

- **Option B (Real LLM Only):** Real `ClaudeA2AExecutor` and
  `GeminiA2AExecutor` with French story prompts. Validates true collaboration
  but is slow (~3-5 min), costly, and potentially flaky from LLM output
  variance.

- **Option C (Hybrid):** Both mock and real layers in the same test file.
  Mock layer catches orchestration regressions cheaply in CI. Real layer
  proves the system works end-to-end when LLM backends are available.

## Constraints

- No production code changes — test-only addition

- Must use existing A2A infrastructure (`create_app`, `_build_client`,
  `_send_message_payload`, executor classes) without modification

- Port range 10100-10109 (currently unused; existing tests use 10050-10099)

- Live tests gated on `shutil.which("claude")` and `shutil.which("gemini")`

- 300s timeout for live tests (matching `TestGoldStandardBidirectional`)

- French prose validation without external language detection libraries

## Implementation

**New file:** `protocol/a2a/tests/test_french_novel_relay.py`

**Two test classes:**

### `TestFrenchNovelRelayMock` (`@pytest.mark.integration`)

A `StoryRelayExecutor(AgentExecutor)` that appends a deterministic French
chapter template to the accumulated story text. Each executor is named after
a Jean-Claude variant (`"Jean-Claude le Boulanger"`, `"Jean-Claude le Critique"`).

3-turn relay:

1. Claude mock begins: produces chapter 1 template with "Croustillant"
1. Gemini mock continues: receives chapter 1, appends chapter 2
1. Claude mock finishes: receives chapters 1+2, appends epilogue

Assertions:

- All 3 task IDs are independent
- Each chapter's text is present in the accumulated output
- Final output contains all 3 chapter markers
- "Croustillant" appears in all chapters (continuity)

### `TestFrenchNovelRelayLive` (`@pytest.mark.integration @pytest.mark.claude @pytest.mark.gemini`)

Real executors with French prompts and Jean-Claude persona:

- **Turn 1 (Claude begins):** French prompt asking to start a story about
  Croustillant in a Parisian boulangerie. Constrained to one paragraph (3-5
  sentences), ending in suspense.

- **Turn 2 (Gemini continues):** Receives chapter 1, prompted to continue with
  a new character encounter. Same length constraint.

- **Turn 3 (Claude finishes):** Receives chapters 1+2, prompted to write an
  epilogue with resolution.

French prose validation (no external libraries):

- Response non-empty, 100-2000 chars

- Contains at least 3 words from a French indicator set (`le, la, les, un, une, de, du, des, et, est, dans, sur, qui, que, pas, avec, pour, mais`)

- Contains "Croustillant" (character continuity)

- Each chapter is distinct from prior chapters (no echo)

### Shared infrastructure

- `_extract_response_text(body)` — helper to extract text from JSON-RPC response
- `_assert_french_prose(text, min_len, max_len)` — validation helper
- `JEAN_CLAUDE_SYSTEM_PROMPT` — shared system prompt constant in French

## Rationale

Option C was chosen because it provides defense-in-depth testing:

- The mock layer is deterministic, fast (\<1s), and can run in CI on every push.
  It validates the 3-turn relay orchestration pattern — that messages chain
  correctly through 3 independent A2A task lifecycles.

- The live layer validates what no mock can: that real LLMs produce coherent
  French narrative prose when given another agent's output as context. This is
  the definitive proof that A2A bidirectional communication works for
  substantive collaborative tasks, not just token-echo exercises.

The Jean-Claude persona and Croustillant story universe provide thematic
continuity with the existing test suite (used in `test_e2e_bridge.py`,
`test_claude.py`, `test_mcp_e2e.py`, and the `.vault/stories/` corpus). The
French language requirement adds a distinctive, culturally memorable dimension
that doubles as a practical multilingual validation.

No production code changes are required because the existing A2A infrastructure
already supports the 3-turn relay pattern — it was simply never tested.

## Consequences

- Adds one new test file (~250-350 lines) with no production code changes

- Mock tests add \<1s to the integration test suite

- Live tests add ~3-5 minutes when both CLIs are available (gated by skipif)

- Establishes the pattern for future multi-turn A2A test scenarios

- French prose assertions are intentionally minimal (word-presence, not
  linguistic analysis) to avoid false negatives from LLM output variance

- The `StoryRelayExecutor` test double may be reusable for future A2A relay
  tests with different themes or languages
