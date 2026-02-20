---
tags: ["#plan", "#french-novel-relay"]
date: 2026-02-19
related:
  - "[[2026-02-19-french-novel-relay-adr]]"
  - "[[2026-02-19-french-novel-relay-test-research]]"
  - "[[2026-02-15-cross-agent-adr]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `french-novel-relay` `p1` plan

Implement a 3-turn collaborative French novel relay test for the A2A protocol.
Two test classes in a single new file validate multi-agent story generation:
a mock layer for CI-safe orchestration testing and a live layer for real
LLM creative collaboration. Per [[2026-02-19-french-novel-relay-adr]], this
is a test-only change with zero production code modifications.

## Proposed Changes

Create `protocol/a2a/tests/test_french_novel_relay.py` containing:

- Module-level helpers and constants (French prompts, validation, response
  extraction) following the patterns established in `test_e2e_a2a.py`
- `StoryRelayExecutor(AgentExecutor)` — deterministic test double that appends
  French chapter templates, reusing the `TaskUpdater` pattern from
  `EchoExecutor`/`PrefixExecutor` in the existing conftest
- `TestFrenchNovelRelayMock` — 3-turn in-process relay with mock executors
- `TestFrenchNovelRelayLive` — 3-turn relay with real Claude and Gemini

All imports, helpers, markers, and structural patterns mirror `test_e2e_a2a.py`
exactly. The file is self-contained (no conftest changes needed).

## Tasks

- Phase 1: File scaffolding and shared infrastructure
    1. Create `protocol/a2a/tests/test_french_novel_relay.py` with module
       docstring, imports, and skip markers. Imports follow the exact pattern
       from `test_e2e_a2a.py`: `from __future__ import annotations`, `shutil`,
       `time`, `uuid`, `httpx`, `pytest`, plus `AgentExecutor`, `RequestContext`,
       `TaskUpdater`, `Part`, `TextPart` from `a2a` SDK, and
       `_make_card`/`create_app` from production code. Define `requires_anthropic`
       and `requires_gemini` skipif markers.
    2. Define `_send_message_payload(text)` and `_build_client(executor, name, port)`
       helpers — identical to `test_e2e_a2a.py` (copy the pattern, these are
       module-local helpers not shared via conftest).
    3. Define `_extract_response_text(body)` helper — extracts text from the
       JSON-RPC response body (`body["result"]["status"]["message"]["parts"][0]["text"]`).
       Returns empty string on any missing key.
    4. Define `FRENCH_WORDS` frozenset containing French indicator words (`le`,
       `la`, `les`, `un`, `une`, `de`, `du`, `des`, `et`, `est`, `dans`, `sur`,
       `qui`, `que`, `pas`, `avec`, `pour`, `mais`).
    5. Define `_assert_french_prose(text, min_len=100, max_len=2000)` validation
       helper. Asserts: non-empty, within length bounds, contains at least 3
       words from `FRENCH_WORDS` (case-insensitive word boundary matching),
       contains "Croustillant".
    6. Define three French prompt constants: `PROMPT_BEGIN` (Turn 1 — Claude
       starts story), `PROMPT_CONTINUE` (Turn 2 — Gemini continues, takes
       `{chapter_1}` placeholder), `PROMPT_FINISH` (Turn 3 — Claude writes
       epilogue, takes `{chapter_1}` and `{chapter_2}` placeholders). Prompts
       are entirely in French per [[2026-02-19-french-novel-relay-test-research]]
       Section 7.

- Phase 2: StoryRelayExecutor and mock test class
    1. Define `StoryRelayExecutor(AgentExecutor)` inline in the test file.
       Constructor takes `chapter_text: str`. The `execute()` method uses
       `TaskUpdater` to emit `start_work()` then `complete()` with the
       chapter text appended to `context.get_user_input()` (separated by
       `"\n\n"`). The `cancel()` method calls `updater.cancel()`. This follows
       the exact pattern of `PrefixExecutor` in conftest.
    2. Define three chapter template constants: `MOCK_CHAPTER_1` (French
       paragraph about Croustillant beginning his journey), `MOCK_CHAPTER_2`
       (French paragraph about meeting a character), `MOCK_EPILOGUE` (French
       resolution paragraph). All contain "Croustillant" for continuity checks.
    3. Implement `TestFrenchNovelRelayMock` class with `@pytest.mark.integration`
       marker and a single async test method `test_three_turn_story_relay`.
       Create 3 `StoryRelayExecutor` instances (one per chapter), wrap each
       in `_build_client()` using ports 10100, 10101, 10102. Execute the 3-turn
       relay: send seed prompt to client 1 → extract chapter 1 → send to
       client 2 → extract chapter 2 → send accumulated to client 3 → extract
       epilogue.
    4. Assertions for mock test: all 3 responses have `state == "completed"`,
       all 3 task IDs are distinct, each chapter text appears in the
       accumulated final output, "Croustillant" appears in each response,
       total relay completes in under 5 seconds.

- Phase 3: Live test class
    1. Implement `TestFrenchNovelRelayLive` class with markers:
       `@pytest.mark.integration`, `@pytest.mark.claude`, `@pytest.mark.gemini`,
       `@pytest.mark.timeout(300)`, `@requires_anthropic`, `@requires_gemini`.
    2. Single async test method `test_three_turn_french_story`. Set up Claude
       executor (`ClaudeA2AExecutor`, model `ClaudeModels.MEDIUM`,
       `root_dir=str(_TEST_ROOT)`, `mode="read-only"`) and Gemini executor
       (`GeminiA2AExecutor`, `root_dir=_TEST_ROOT`, model `GeminiModels.LOW`,
       `agent_name="vaultspec-researcher"`). Wrap each in `_build_client()`
       using ports 10105 and 10106.
    3. Turn 1: Send `PROMPT_BEGIN` to Claude client. Extract `chapter_1` via
       `_extract_response_text()`. Assert state completed. Call
       `_assert_french_prose(chapter_1)`. Print timing.
    4. Turn 2: Format `PROMPT_CONTINUE` with `chapter_1`. Send to Gemini client.
       Extract `chapter_2`. Assert state completed. Call
       `_assert_french_prose(chapter_2)`. Assert `chapter_2 != chapter_1`
       (no echo). Print timing.
    5. Turn 3: Format `PROMPT_FINISH` with `chapter_1` and `chapter_2`. Send to
       Claude client. Extract `epilogue`. Assert state completed. Call
       `_assert_french_prose(epilogue)`. Assert epilogue is distinct from both
       prior chapters. Print total timing across all 3 turns.

- Phase 4: Verification
    1. Run mock tests: `pytest protocol/a2a/tests/test_french_novel_relay.py -k Mock -v`
       — must pass without any LLM backend.
    2. Run live tests (if both CLIs available):
       `pytest protocol/a2a/tests/test_french_novel_relay.py -k Live -v`
       — must produce 3 chapters of French prose about Croustillant.
    3. Run the full A2A test suite to confirm no regressions:
       `pytest protocol/a2a/tests/ -v`

## Parallelization

This is a single-file implementation. Phases 1-3 are sequential (each builds
on the prior). Phase 4 (verification) runs after implementation is complete.

The task is well-suited for a single `vaultspec-standard-executor` agent given
the clear specification and zero production code changes. No parallelization
needed.

## Verification

**Success criteria per [[2026-02-19-french-novel-relay-adr]]:**

- `TestFrenchNovelRelayMock.test_three_turn_story_relay` passes with no LLM
  backend. Validates: 3-turn message chaining, independent task IDs, chapter
  accumulation, "Croustillant" continuity, completes in <5s.

- `TestFrenchNovelRelayLive.test_three_turn_french_story` passes when both
  Claude and Gemini CLIs are on PATH. Validates: real French prose output from
  both providers, character continuity across agents, distinct chapter content,
  length within bounds, French word presence, completes within 300s timeout.

- Full `protocol/a2a/tests/` suite runs without regressions — existing gold
  standard and integration tests still pass.

- No production code changes, no new dependencies, no conftest modifications.

**Honest assessment:** The mock test is fully deterministic and will reliably
catch orchestration regressions. The live test depends on LLM output and may
occasionally fail if an agent refuses the creative writing task, responds in
English, or drops the character name. The `_assert_french_prose` validation is
intentionally lenient to minimize false negatives while still distinguishing
French narrative from error responses.
