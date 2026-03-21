---
tags:
  - '#exec'
  - '#french-novel-relay'
date: '2026-02-19'
related:
  - '[[2026-02-19-french-novel-relay-p1-plan]]'
---

# `french-novel-relay` `p1` implementation step record

## Files Created

- `.vaultspec/lib/src/protocol/a2a/tests/test_french_novel_relay.py`

No production code was modified. No existing files were changed.

## Description

Implemented the 3-turn collaborative French novel relay test in a single
self-contained file. All four phases of the plan were completed sequentially.

### Phase 1 — Scaffolding

Module docstring, imports mirroring `test_e2e_a2a.py` exactly, `requires_anthropic`
and `requires_gemini` skipif markers, `_send_message_payload` and `_build_client`
helpers (exact copies of the source pattern), `_extract_response_text` (safe
try/except on `KeyError, IndexError, TypeError`), `FRENCH_WORDS` frozenset (18
indicator words), `_assert_french_prose` validator, and three French prompt
constants (`PROMPT_BEGIN`, `PROMPT_CONTINUE`, `PROMPT_FINISH`).

### Phase 2 — StoryRelayExecutor and mock test class

`StoryRelayExecutor(AgentExecutor)` follows the `PrefixExecutor` pattern from
`conftest.py`: takes `chapter_text: str`, emits `start_work()` then `complete()`
with input + `"\n\n"` + chapter text. Three `MOCK_CHAPTER_*` constants in French,
all containing "Croustillant". `TestFrenchNovelRelayMock` with
`@pytest.mark.integration`, single async test `test_three_turn_story_relay` using
ports 10100-10102.

### Phase 3 — Live test class

`TestFrenchNovelRelayLive` with markers `integration`, `claude`, `gemini`,
`timeout(300)`, `requires_anthropic`, `requires_gemini`. Single async test
`test_three_turn_french_story` using `ClaudeA2AExecutor` (port 10105) and
`GeminiA2AExecutor` (port 10106). 3-turn relay: Claude begins → Gemini continues
→ Claude finishes. `_assert_french_prose` called on each chapter. Distinctness
assertions on all three outputs. Per-turn and total timing printed.

### Phase 4 — Verification

Mock test run result:

```
PASSED .vaultspec/lib/src/protocol/a2a/tests/test_french_novel_relay.py::TestFrenchNovelRelayMock::test_three_turn_story_relay
1 passed, 1 deselected in 0.08s
```

No regressions. Mock relay completed in 0.08s (well under the 5s threshold).

## Code Review

Manual review conducted against the `vaultspec-code-reviewer` checklist:

- Import style, ordering, and skip markers match `test_e2e_a2a.py` exactly.
- `_extract_response_text` is safe — catches `KeyError`, `IndexError`, `TypeError`.
- `_assert_french_prose` uses `re.search` with `\b` word boundaries; no ReDoS risk.
- Port allocation 10100-10106 does not conflict with existing test range 10050-10099.
- `StoryRelayExecutor` follows `PrefixExecutor` pattern exactly (assertions, lifecycle).
- All mock chapter constants contain "Croustillant".
- Live executor imports deferred inside test method (matches gold standard pattern).
- No production code changes, no new dependencies, no conftest modifications.

**Verdict: PASS.**
