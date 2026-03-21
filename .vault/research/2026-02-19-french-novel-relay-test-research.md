---
tags:
  - '#research'
  - '#french-novel-relay'
date: '2026-02-19'
related:
  - '[[2026-02-15-cross-agent-adr]]'
  - '[[2026-02-15-a2a-adr]]'
  - '[[2026-02-07-a2a-research]]'
---

# `french-novel-relay` research: 3-Turn Collaborative French Story Test via A2A

Research into implementing a multi-agent collaborative French novel relay test
that validates true bidirectional A2A communication by having agents write a
story together — Agent A begins, Agent B continues, Agent A finishes.

## Findings

### 1. Current State of the Test Suite

A full audit of ~75 test files across the codebase reveals three testing layers
for agent-to-agent communication:

**Layer 1 — Unit (no LLM):** `PrefixExecutor`-based in-process tests simulate
cross-delegation by chaining output strings. `test_claude_gemini_bidirectional`
in `test_e2e_a2a.py` validates `"[Claude] [Gemini] analyze the results"`.
Deterministic but exercises no real reasoning.

**Layer 2 — Gold Standard (real LLM):** `TestGoldStandardBidirectional` in
`test_e2e_a2a.py` chains real Claude and Gemini via sequential output forwarding.
Uses exact-match tokens (`GEMINI_CONFIRMED`, `CLAUDE_RECEIVED_GEMINI`) rather
than creative content. The code explicitly notes: *"True cross-delegation
requires MCP tool injection, which is Phase 6 scope."*

**Layer 3 — Missing:** No test exercises multi-turn creative relay where agents
produce and validate narrative prose. No test validates French language output.
No test has Agent A's output meaningfully consumed and extended by Agent B.

### 2. Existing Jean-Claude Infrastructure

The Jean-Claude persona is deeply embedded as a test fixture identity:

| Component              | Location                                       | Content                                                                  |
| ---------------------- | ---------------------------------------------- | ------------------------------------------------------------------------ |
| Identity fingerprint   | `test_claude.py`, `test_gemini.py`             | `"You are Jean-Claude, a helpful assistant."` — assert name in response  |
| Le Critique Pâtissier  | `test_e2e_bridge.py`                           | Full persona: French pastry critic, writes about sentient baked goods    |
| French Baker           | `test_mcp_protocol.py`, orchestration conftest | `"Bonjour! I am Jean-Claude, your French Baker."` — round-trip assertion |
| Le Croissant Solitaire | `test-project/.vault/stories/`                 | 3 chapters + epilogue of French prose about Croustillant the croissant   |

The story corpus is rich: Ch1 (La Mélancolie de Croustillant), Ch2 (La Nuit et
le Chat Philosophe), and Épilogue (Le Choix de Croustillant). All are in fluent
French with Parisian settings, philosophical themes, and a sentient-pastry
protagonist.

### 3. A2A Protocol Capabilities Analysis

From `protocol/a2a/`:

- **`create_app(executor, card)`** — wraps any `AgentExecutor` in a Starlette
  ASGI app with `DefaultRequestHandler` + `InMemoryTaskStore`

- **`_send_message_payload(text)`** — builds JSON-RPC `message/send` requests

- **`_build_client(executor, name, port)`** — creates in-process `httpx.AsyncClient`
  backed by `ASGITransport`

- **`ClaudeA2AExecutor`** — real Claude via `claude-agent-sdk`, DI-injectable
  `client_factory` and `options_factory`

- **`GeminiA2AExecutor`** — real Gemini via `run_subagent()`, DI-injectable
  `run_subagent` callable

- **`PrefixExecutor(prefix)`** — deterministic test double, prepends string

- **`EchoExecutor`** — returns `"Echo: {text}"`

The gold standard pattern (from `TestGoldStandardBidirectional`):

```
Step 1: Send message to Agent A → get response_text_a
Step 2: Send f"Context: '{response_text_a}'. Your task: ..." to Agent B → get response_text_b
```

This pattern trivially extends to 3 turns:

```
Step 1: Agent A begins story → chapter_1
Step 2: Agent B receives chapter_1, continues → chapter_2
Step 3: Agent A receives chapter_1 + chapter_2, finishes → epilogue
```

### 4. Design Options

#### Option A: In-Process Mock Relay (No LLM)

A new `StoryRelayExecutor(AgentExecutor)` that appends a chapter marker and
forwards the accumulated text. Deterministic, fast (\<1s), no API cost.

```python
class StoryRelayExecutor(AgentExecutor):
    def __init__(self, agent_name: str, chapter_template: str):
        self._name = agent_name
        self._template = chapter_template

    async def execute(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        prior_text = context.get_user_input()
        chapter = self._template.format(prior=prior_text, agent=self._name)
        await updater.start_work()
        await updater.complete(
            message=updater.new_agent_message(
                parts=[Part(root=TextPart(text=chapter))]
            )
        )
```

**Pros:** Fast, deterministic, tests the 3-turn relay orchestration pattern
without LLM cost or flakiness. Can validate message chaining, task ID
independence, and protocol correctness.

**Cons:** No real narrative quality. No French language validation. Tests
plumbing, not communication.

#### Option B: Real LLM Relay (Claude + Gemini)

Extend `TestGoldStandardBidirectional` to 3 turns with French story prompts.
Jean-Claude persona injected via system prompt on both executors.

```python

# Turn 1: Claude begins

prompt_1 = (
    "Tu es Jean-Claude, critique pâtissier. Commence une histoire en français "
    "sur un croissant nommé Croustillant dans une boulangerie parisienne. "
    "Écris exactement un paragraphe (3-5 phrases). Termine par une situation "
    "de suspense. Réponds uniquement avec l'histoire, sans explication."
)

# Turn 2: Gemini continues

prompt_2 = f"Voici le début d'une histoire:\n\n{chapter_1}\n\nContinue..."

# Turn 3: Claude finishes

prompt_3 = f"Voici l'histoire jusqu'ici:\n\n{chapter_1}\n\n{chapter_2}\n\nTermine..."
```

**Pros:** Validates real agent reasoning, French prose output, narrative
coherence across agents, the full A2A stack. This is the gold standard test
that proves agents can truly collaborate.

**Cons:** Slow (~60-90s per turn, ~3-5 min total), API cost, potential flakiness
from LLM output variance. Requires both Claude and Gemini CLIs on PATH.

#### Option C: Hybrid — Mock + Real (Recommended)

Two test classes in the same file:

1. `TestFrenchNovelRelayMock` (`@pytest.mark.integration`) — 3-turn relay with
   `StoryRelayExecutor` mock executors that produce deterministic French chapter
   templates. Validates orchestration correctness, message chaining, task
   independence, and the relay pattern itself. Fast, no LLM.

1. `TestFrenchNovelRelayLive` (`@pytest.mark.integration @pytest.mark.claude @pytest.mark.gemini @pytest.mark.timeout(300)`) — 3-turn relay with real
   `ClaudeA2AExecutor` and `GeminiA2AExecutor`. French story prompts with
   Jean-Claude persona. Validates real bidirectional creative collaboration.

The mock layer catches orchestration regressions cheaply. The live layer proves
the system actually works end-to-end.

### 5. French Prose Validation Strategy

For the live test, we need to validate that the output is actually French prose
continuing a story (not just an echo or refusal). Options:

**Minimal validation (recommended for initial implementation):**

- Assert response is non-empty and exceeds minimum length (>100 chars)

- Assert response contains at least one French indicator word from a set
  (`{"le", "la", "les", "un", "une", "de", "du", "des", "et", "est", "dans", "sur", "qui", "que", "pas", "avec", "pour", "son", "ses", "mais"}`)

- Assert response contains the character name "Croustillant" (continuity check)

- Assert each subsequent chapter is distinct from prior chapters (no echo)

**Why not use language detection libraries?** Adding `langdetect` or `lingua`
as a test dependency solely for one assertion is over-engineering. A simple
word-presence check is sufficient to distinguish French prose from English
refusals, error messages, or empty responses.

### 6. Test Infrastructure Changes Required

**New file:** `protocol/a2a/tests/test_french_novel_relay.py`

**New in conftest.py:**

- `StoryRelayExecutor` class (or inline in test file if small enough)
- No new fixtures needed — existing `_build_client`, `_send_message_payload`,
  `_make_card` from the test module pattern are sufficient

**No production code changes required.** The existing A2A infrastructure
supports the 3-turn pattern natively — it's just a test file.

**Port allocation:** Use 10100-10109 range (currently unused; existing tests
use 10050-10099).

**Markers:**

- Mock tests: `@pytest.mark.integration`
- Live tests: `@pytest.mark.integration @pytest.mark.claude @pytest.mark.gemini`
- Timeout: 300s for live (matching `TestGoldStandardBidirectional`)

### 7. Story Prompt Design

The prompts should be:

- **In French** — to validate French output

- **Constrained** — "exactly one paragraph, 3-5 sentences" to keep LLM costs
  down and responses predictable

- **Anchored** — reference "Croustillant" by name for continuity validation

- **Suspenseful** — each chapter ends with a hook for the next agent

Example 3-turn prompt sequence:

**Turn 1 (Claude begins):**

> Tu es Jean-Claude, un critique pâtissier français avec un don pour l'écriture
> dramatique. Commence une histoire en français sur un croissant nommé
> Croustillant qui vit dans une boulangerie parisienne. Écris exactement un
> paragraphe (3-5 phrases). Termine par une situation de suspense. Réponds
> uniquement avec l'histoire.

**Turn 2 (Gemini continues):**

> Tu es Jean-Claude, un critique pâtissier français. Voici le début d'une
> histoire écrite par un collègue:
>
> {chapter_1}
>
> Continue cette histoire avec exactement un paragraphe (3-5 phrases).
> Croustillant doit rencontrer un nouveau personnage. Termine par un moment
> de tension. Réponds uniquement avec la suite de l'histoire.

**Turn 3 (Claude finishes):**

> Tu es Jean-Claude, un critique pâtissier français. Voici une histoire en
> deux parties écrite collaborativement:
>
> {chapter_1}
>
> {chapter_2}
>
> Écris l'épilogue de cette histoire en exactement un paragraphe (3-5 phrases).
> Croustillant doit trouver une résolution. Réponds uniquement avec l'épilogue.

### 8. Relationship to Existing Tests

The new test file extends the pattern established by `TestGoldStandardBidirectional`
but makes three key advances:

1. **3 turns instead of 2** — validates that the relay can continue beyond a
   single handoff

1. **Creative content instead of tokens** — validates that agents produce
   meaningful output that builds on prior context, not just echo fingerprints

1. **French language** — validates multilingual capability and adds a
   distinctively memorable test identity

It does NOT replace existing gold standard tests (which validate exact-match
tokens and are more deterministic). It complements them.

### 9. Risk Assessment

| Risk                         | Likelihood | Mitigation                                                     |
| ---------------------------- | ---------- | -------------------------------------------------------------- |
| LLM refuses to write fiction | Low        | Explicit persona + "Réponds uniquement avec l'histoire"        |
| LLM responds in English      | Medium     | French-word presence assertion; prompts are entirely in French |
| Output too long / too short  | Medium     | Length bounds (100-2000 chars) in assertions                   |
| Character name dropped       | Low        | Explicit prompt instruction + assertion                        |
| API timeout                  | Medium     | 300s timeout; `pytest.mark.timeout`; skip if CLIs absent       |
| Flaky output format          | Medium     | Minimal validation (no structural parsing)                     |

### 10. Recommendation

**Implement Option C (Hybrid).** The mock relay proves the orchestration pattern
works and catches regressions cheaply. The live relay proves the agents can
truly collaborate in French. Both live in the same file
(`test_french_novel_relay.py`) with clear marker separation.

The mock layer runs in CI on every push. The live layer runs when both CLIs are
available (developer machines, dedicated integration environments).

No production code changes are needed. The test leverages existing A2A
infrastructure (`create_app`, `_build_client`, `_send_message_payload`,
`ClaudeA2AExecutor`, `GeminiA2AExecutor`) without modification.
