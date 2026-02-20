---
tags:
  - "#exec"
  - "#french-novel-relay"
date: 2026-02-20
related:
  - "[[2026-02-19-french-novel-relay-adr]]"
---

# `french-novel-relay` code review

**Status:** `REVISION REQUIRED`

## Audit Context

- **ADR:** `[[2026-02-19-french-novel-relay-adr]]`
- **Scope:** `.vaultspec/lib/src/protocol/a2a/tests/test_french_novel_relay.py` (single new test file; no production code changes)

---

## Findings

### Critical / High (Must Fix)

- **[HIGH]** `_assert_french_prose()` line 131 — The `"Croustillant" in text` guard is applied unconditionally to all three turns in the live test. The `PROMPT_CONTINUE` sent to Gemini (Turn 2) injects chapter 1 as context but does not command the LLM to use the character name verbatim. If Gemini paraphrases ("le croissant", "lui", "il") the assertion fails spuriously. This is a real flakiness risk on live runs. The ADR explicitly says assertions should be "intentionally minimal to avoid false negatives from LLM output variance" — this assertion is not minimal.

- **[HIGH]** `_assert_french_prose()` line 117 — `max_len: int = 2000` imposes a hard character ceiling on LLM output. The Turn 3 prompt (`PROMPT_FINISH`) embeds two full paragraphs of prior chapter text inside the prompt string, and some LLMs include echoed context in their response. A response just over 2000 chars — well within normal paragraph range — will trigger a spurious failure. The ADR states "intentionally minimal" assertions; the upper bound contradicts this.

- **[HIGH]** `StoryRelayExecutor.execute()` line 183 / `cancel()` line 196 — The `event_queue` parameter is untyped. Every executor in the codebase (`EchoExecutor`, `PrefixExecutor` in `conftest.py` lines 31/43 and 56/68) annotates `event_queue: EventQueue` via a `TYPE_CHECKING` import guard. This is the established convention and is missing here, degrading type-checker coverage on the public `AgentExecutor` interface.

---

### Medium / Low (Recommended)

- **[MEDIUM]** `StoryRelayExecutor.execute()` line 188 — The accumulating payload design (`f"{text}\n\n{self._chapter_text}"`) means each turn's response contains all prior input plus the new chapter. The variable names `chapter_1`, `chapter_2`, `epilogue` suggest isolated chapter content, but each contains the entire accumulated relay string. A clarifying comment stating this is intentional relay chaining would prevent misreading by future maintainers.

- **[MEDIUM]** `test_three_turn_story_relay` line 302 — `assert relay_elapsed < 5.0` is aggressive for a CI runner. Three sequential ASGI in-process round-trips under Windows with process scheduling variance can sporadically exceed 5s. The existing canonical tests in `test_e2e_a2a.py` impose no timing assertions on mock relays. Recommend raising to 10s or removing the bound.

- **[MEDIUM]** ADR Shared Infrastructure section specifies a `JEAN_CLAUDE_SYSTEM_PROMPT` named constant. The implementation embeds the Jean-Claude persona inline in each of `PROMPT_BEGIN`, `PROMPT_CONTINUE`, and `PROMPT_FINISH`, tripling the persona text with no shared reference. The constant described in the ADR does not exist. Minor spec drift; the inline approach is functional but violates DRY and the ADR's stated design.

- **[MEDIUM]** `test_three_turn_french_story` lines 402-403 — `epilogue != chapter_1` and `epilogue != chapter_2` guard verbatim echo. The symmetric `chapter_2 != chapter_1` check is present on line 383. Coverage is adequate per the ADR's "intentionally minimal" stance but noted.

- **[LOW]** `_send_message_payload()` and `_build_client()` are byte-for-byte duplicates of the identically named functions in `test_e2e_a2a.py`. Same for `requires_anthropic` / `requires_gemini` skip markers. These should be consolidated into `conftest.py` in a follow-up to remove the duplication. The ADR constraint "without modification to existing files" applies to production code, not conftest.

- **[LOW]** Port 10099 appears in the `_build_client` default parameter (line 70) but is never exercised — all callers provide explicit ports (10100-10106). No conflict with existing tests (10050-10099). Cosmetic.

- **[LOW]** `import time` is present and used only for `time.monotonic()` timing measurements in both test methods. In the live test, timing variables are printed but not asserted, which is correct given the absence of a live-test timing SLA. No issue.

---

## Recommendations

The following changes are required before merge. All three HIGH findings are small, surgical fixes.

**1. Parameterize the character-name check (HIGH — Flakiness)**

In `_assert_french_prose`, make the "Croustillant" check conditional:

```python
def _assert_french_prose(
    text: str,
    min_len: int = 100,
    max_len: int = 2000,
    check_character: bool = True,
) -> None:
    ...
    if check_character:
        assert "Croustillant" in text, ...
```

Call the validator in the live test as `_assert_french_prose(chapter_2, check_character=False)` for the Gemini turn, since the prompt does not enforce verbatim character naming.

**2. Remove or raise the max_len ceiling (HIGH — Flakiness)**

Replace `max_len: int = 2000` with `max_len: int = 5000`, or remove the upper-bound assertion entirely. The lower-bound check (`min_len`) is sufficient to catch empty/truncated responses.

**3. Add EventQueue type annotation (HIGH — Convention)**

Add at the top of the file:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from a2a.server.events import EventQueue
```

Annotate both `StoryRelayExecutor` methods: `async def execute(self, context: RequestContext, event_queue: "EventQueue") -> None`.

**Follow-up (not blocking if HIGH items are fixed):**

- Add a `JEAN_CLAUDE_SYSTEM_PROMPT` constant or update the ADR to document the inline approach.
- Consolidate `_send_message_payload`, `_build_client`, `requires_anthropic`, `requires_gemini` into `conftest.py`.
- Add accumulation comment to `StoryRelayExecutor.execute()`.
- Raise the 5s mock timing ceiling to 10s.

---

## Notes

The structural decisions in this file are correct. `StoryRelayExecutor` is a valid `AgentExecutor` implementation: `execute()` calls `start_work()` before `complete()`, `cancel()` calls `updater.cancel()`, and both methods assert `task_id` / `context_id` non-None before constructing the updater, matching the conftest pattern exactly. The port range (10100-10106) is confirmed clear of all existing tests. The `@pytest.mark.integration` / `@pytest.mark.claude` / `@pytest.mark.gemini` / `@pytest.mark.timeout(300)` / `@requires_anthropic` / `@requires_gemini` marker stack on `TestFrenchNovelRelayLive` is correct. Mock chapter strings (`MOCK_CHAPTER_1`, `MOCK_CHAPTER_2`, `MOCK_EPILOGUE`) are distinct and all contain "Croustillant". Task ID independence assertions on lines 287-289 are complete. No production code was modified.

The two flakiness HIGHs and one convention HIGH are the only blockers. They are small, targeted changes and do not require restructuring the file.
