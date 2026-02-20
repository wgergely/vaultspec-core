---
tags: ["#exec", "#french-novel-relay"]
date: 2026-02-19
related:
  - "[[2026-02-19-french-novel-relay-p1-plan]]"
  - "[[2026-02-19-french-novel-relay-adr]]"
  - "[[2026-02-19-french-novel-relay-test-research]]"
---

# `french-novel-relay` `p1` summary

3-turn collaborative French novel relay test implemented and reviewed.

- Created: `protocol/a2a/tests/test_french_novel_relay.py`

## Description

Implemented a single new test file containing:

- `StoryRelayExecutor(AgentExecutor)` — deterministic test double that appends
  French chapter templates, following the `PrefixExecutor` pattern
- `_assert_french_prose()` — French prose validation helper with configurable
  character check and length bounds (100-5000 chars)
- `_extract_response_text()` — JSON-RPC response text extraction helper
- `FRENCH_WORDS` frozenset — 18 French indicator words for language detection
- Three French prompt constants (`PROMPT_BEGIN`, `PROMPT_CONTINUE`, `PROMPT_FINISH`)
- Three mock chapter constants (all containing "Croustillant")
- `TestFrenchNovelRelayMock` — deterministic 3-turn relay, ports 10100-10102
- `TestFrenchNovelRelayLive` — real Claude + Gemini relay, ports 10105-10106

Zero production code changes. Zero conftest modifications. Zero new dependencies.

Post-review fixes applied for 3 HIGH findings:
- Added `TYPE_CHECKING` guard and `EventQueue` annotation on executor methods
- Added `check_character` parameter to `_assert_french_prose()` (disabled for
  Gemini turn to avoid spurious failures from pronoun usage)
- Raised `max_len` from 2000 to 5000 (LLMs may echo context in responses)
- Relaxed mock timing assertion from 5s to 10s for Windows CI

## Tests

- `TestFrenchNovelRelayMock::test_three_turn_story_relay` — PASSED (0.12s)
- Full A2A suite (57 tests) — ALL PASSED, 0 regressions, 12 deselected (LLM-gated)
- Live test (`TestFrenchNovelRelayLive`) requires both Claude and Gemini CLIs
  on PATH — gated by `@requires_anthropic` / `@requires_gemini` skipif markers
